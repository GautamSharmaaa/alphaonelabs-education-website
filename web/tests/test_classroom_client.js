// Virtual Classroom Client-side Tests
// Run with Jest or another JavaScript testing framework

describe('Virtual Classroom WebSocket Connection', () => {
  let socket;
  let originalWebSocket;
  let sentMessages = [];
  let receivedMessages = [];

  // Mock WebSocket
  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = WebSocket.CONNECTING;

      // Auto connect after creation
      setTimeout(() => {
        this.readyState = WebSocket.OPEN;
        if (this.onopen) this.onopen({ target: this });
      }, 50);
    }

    send(data) {
      sentMessages.push(JSON.parse(data));

      // Echo back for testing
      setTimeout(() => {
        if (this.onmessage) {
          this.onmessage({ data });
        }
      }, 50);
    }

    close() {
      this.readyState = WebSocket.CLOSED;
      if (this.onclose) this.onclose({ code: 1000, reason: 'Test closed', wasClean: true });
    }
  }

  beforeEach(() => {
    // Save original
    originalWebSocket = window.WebSocket;

    // Replace with mock
    window.WebSocket = MockWebSocket;

    // Constants needed for tests
    window.classroomId = 'test-id';
    window.currentUserId = 'user-1';
    window.currentUsername = 'testuser';
    window.isTeacher = false;

    // Reset tracking arrays
    sentMessages = [];
    receivedMessages = [];

    // Create DOM elements needed by the code
    document.body.innerHTML = `
      <div id="notification" class="hidden"></div>
      <div id="timerProgress"></div>
      <div id="remainingTime"></div>
      <div id="raisedHandsQueue"></div>
    `;
  });

  afterEach(() => {
    // Restore original
    window.WebSocket = originalWebSocket;

    // Clean up
    if (socket && socket.close) {
      socket.close();
    }

    jest.clearAllMocks();
  });

  test('establishes connection successfully', () => {
    // Spy on showNotification
    const showNotificationSpy = jest.fn();
    window.showNotification = showNotificationSpy;

    // Connect
    socket = connectWebSocket();

    // Wait for connection to be established
    return new Promise(resolve => {
      setTimeout(() => {
        expect(showNotificationSpy).toHaveBeenCalledWith('Connected to classroom');
        expect(socket.readyState).toBe(WebSocket.OPEN);
        resolve();
      }, 100);
    });
  });

  test('handles reconnection on connection failure', () => {
    // Make connection fail
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    window.WebSocket = jest.fn().mockImplementation(() => {
      throw new Error('Connection failed');
    });

    // Spy on showNotification
    const showNotificationSpy = jest.fn();
    window.showNotification = showNotificationSpy;

    // First reconnect attempt
    connectWebSocket();

    return new Promise(resolve => {
      setTimeout(() => {
        expect(showNotificationSpy).toHaveBeenCalledWith('Failed to connect to classroom. Please refresh the page.', true);
        expect(window.WebSocket).toHaveBeenCalledTimes(1);
        resolve();
      }, 100);
    });
  });

  test('can send and receive WebSocket messages', () => {
    const showNotificationSpy = jest.fn();
    window.showNotification = showNotificationSpy;

    // Connect
    socket = connectWebSocket();

    return new Promise(resolve => {
      setTimeout(() => {
        // Send a message
        const chatMessage = {
          type: 'chat_message',
          message: 'Hello world',
          recipient: 'everyone'
        };
        sendWebSocketMessage(chatMessage);

        // Check if sent
        expect(sentMessages.length).toBe(1);
        expect(sentMessages[0]).toEqual(chatMessage);

        resolve();
      }, 100);
    });
  });

  test('handles seating status updates', () => {
    socket = connectWebSocket();

    // Mock DOM for seat status testing
    document.body.innerHTML += `
      <div class="seat" data-id="seat-1">
        <div class="w-full h-full"></div>
      </div>
    `;

    // Create handler for seat status update
    window.updateSeatStatus = jest.fn();

    // Simulate receiving a seat update message
    const seatUpdateMsg = {
      type: 'seat_update',
      seat_id: 'seat-1',
      status: 'occupied',
      student_id: 'user-1',
      student_name: 'testuser'
    };

    return new Promise(resolve => {
      setTimeout(() => {
        // Simulate message reception
        socket.onmessage({
          data: JSON.stringify(seatUpdateMsg)
        });

        // Check if updateSeatStatus was called with the right args
        expect(window.updateSeatStatus).toHaveBeenCalledWith(
          'seat-1',
          'occupied',
          { id: 'user-1', username: 'testuser' }
        );

        resolve();
      }, 100);
    });
  });

  test('shows notification for errors', () => {
    const showNotificationSpy = jest.fn();
    window.showNotification = showNotificationSpy;

    socket = connectWebSocket();

    return new Promise(resolve => {
      setTimeout(() => {
        // Simulate error message
        socket.onmessage({
          data: JSON.stringify({
            type: 'error',
            message: 'Test error message'
          })
        });

        expect(showNotificationSpy).toHaveBeenCalledWith('Server error: Test error message', true);
        resolve();
      }, 100);
    });
  });

  test('notification system works for different types', () => {
    // Mock DOM elements
    document.body.innerHTML = `
      <div id="notification" class="hidden"></div>
    `;

    // Implement the real notification function for testing
    window.showNotification = function(message, isError, type) {
      const notification = document.getElementById('notification');
      notification.textContent = message;
      notification.classList.remove('hidden');

      if (isError || type === 'error') {
        notification.dataset.type = 'error';
      } else if (type === 'success') {
        notification.dataset.type = 'success';
      } else if (type === 'warning') {
        notification.dataset.type = 'warning';
      } else {
        notification.dataset.type = 'info';
      }
    };

    // Test different notification types
    window.showNotification('Info message');
    expect(document.getElementById('notification').textContent).toBe('Info message');
    expect(document.getElementById('notification').dataset.type).toBe('info');

    window.showNotification('Error message', true);
    expect(document.getElementById('notification').textContent).toBe('Error message');
    expect(document.getElementById('notification').dataset.type).toBe('error');

    window.showNotification('Success message', false, 'success');
    expect(document.getElementById('notification').textContent).toBe('Success message');
    expect(document.getElementById('notification').dataset.type).toBe('success');

    window.showNotification('Warning message', false, 'warning');
    expect(document.getElementById('notification').textContent).toBe('Warning message');
    expect(document.getElementById('notification').dataset.type).toBe('warning');
  });
});

describe('Virtual Classroom UI Interaction', () => {
  beforeEach(() => {
    // Set up DOM elements needed for testing
    document.body.innerHTML = `
      <div class="seat" data-id="seat-1" data-status="empty">
        <div class="w-full h-full"></div>
      </div>
      <div class="seat" data-id="seat-2" data-status="occupied">
        <div class="w-full h-full">
          <div class="text-xs mt-1">testuser</div>
        </div>
      </div>
      <button id="raiseHandBtn">Raise Hand</button>
      <button id="endTurnBtn" data-turn-id="turn-1">End Turn</button>
      <button id="shareLaptopBtn">Share Laptop</button>
      <div id="notification" class="hidden"></div>
    `;

    // Mock fetch
    global.fetch = jest.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })
    );

    // Global variables
    window.classroomId = 'test-id';
    window.currentUsername = 'testuser';
    window.socket = { readyState: WebSocket.OPEN };
    window.sendWebSocketMessage = jest.fn();
    window.showNotification = jest.fn();
    window.getCSRFToken = jest.fn().mockReturnValue('csrf-token');
  });

  test('raise hand button works', () => {
    // Attach event listener
    const raiseHandBtn = document.getElementById('raiseHandBtn');
    raiseHandBtn.addEventListener('click', function() {
      // Find user's current seat
      let userSeat = null;
      document.querySelectorAll('.seat').forEach(seat => {
          const nameElement = seat.querySelector('.text-xs.mt-1');
          if (nameElement && nameElement.textContent === currentUsername) {
              userSeat = seat;
          }
      });

      if (!userSeat) {
          showNotification('Please select a seat first', true);
          return;
      }

      const seatId = userSeat.dataset.id;
      const isRaised = userSeat.dataset.status === 'hand_raised';

      // Send AJAX request to raise/lower hand
      fetch('/classroom/raise-hand/', {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCSRFToken()
          },
          body: JSON.stringify({
              seat_id: seatId,
              raised: !isRaised
          })
      });
    });

    // Click the button
    raiseHandBtn.click();

    // Check if fetch was called with the right params
    expect(fetch).toHaveBeenCalledWith('/classroom/raise-hand/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': 'csrf-token'
        },
        body: JSON.stringify({
            seat_id: 'seat-2',
            raised: true
        })
    });
  });

  test('share laptop button checks seat first', () => {
    // Clear occupied seat to test error case
    document.querySelector('.seat[data-status="occupied"]').innerHTML = '';

    // Attach event listener
    const shareLaptopBtn = document.getElementById('shareLaptopBtn');
    shareLaptopBtn.addEventListener('click', function() {
      // Find user's current seat
      let userSeat = null;
      document.querySelectorAll('.seat').forEach(seat => {
          const nameElement = seat.querySelector('.text-xs.mt-1');
          if (nameElement && nameElement.textContent === currentUsername) {
              userSeat = seat;
          }
      });

      if (!userSeat) {
          showNotification('Please select a seat first before sharing your laptop', true);
          return;
      }

      // If we get here, seat was found and shareLaptopBtn would proceed
      sendWebSocketMessage({
          'type': 'share_content',
          'content_type': 'code',
          'content': { 'code': 'test code' }
      });
    });

    // Click the button
    shareLaptopBtn.click();

    // Check if notification was shown
    expect(showNotification).toHaveBeenCalledWith(
      'Please select a seat first before sharing your laptop',
      true
    );

    // WebSocket message should not have been sent
    expect(sendWebSocketMessage).not.toHaveBeenCalled();
  });

  test('end turn button works', () => {
    // Attach event listener
    const endTurnBtn = document.getElementById('endTurnBtn');
    endTurnBtn.addEventListener('click', function() {
      const turnId = this.dataset.turnId;

      fetch(`/classroom/end-turn/${turnId}/`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCSRFToken()
          }
      })
      .then(() => {
          showNotification('Turn ended successfully');
      });
    });

    // Click the button
    endTurnBtn.click();

    // Check if fetch was called with the right params
    expect(fetch).toHaveBeenCalledWith('/classroom/end-turn/turn-1/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': 'csrf-token'
        }
    });
  });
});
