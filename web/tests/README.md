# Virtual Classroom Tests

This directory contains tests for the Virtual Classroom functionality of the AlphaOne Labs Education Website.

## Backend Tests

The backend tests are in `test_virtual_classroom.py` and test the Django views, models, and WebSocket consumers.

### Running the Backend Tests

```bash
# From the project root
python manage.py test web.tests.test_virtual_classroom
```

## Frontend Tests

The frontend tests are in `test_classroom_client.js` and test the client-side JavaScript functionality.

### Running the Frontend Tests

To run the frontend tests, you'll need to have Jest installed:

```bash
# Install Jest globally if you haven't already
npm install -g jest

# Or if you prefer to use npx
npx jest web/tests/test_classroom_client.js
```

You can also add these tests to your package.json:

```json
{
  "scripts": {
    "test:classroom": "jest web/tests/test_classroom_client.js"
  }
}
```

Then run with:

```bash
npm run test:classroom
```

## What's Tested

### Backend Tests

1. **VirtualClassroomViewsTests**: Tests the Django views for the virtual classroom
   - Classroom page loads correctly for teachers and students
   - Students can select seats
   - Students can raise hands
   - Teachers can call on students who raised hands
   - Teachers can start update rounds

2. **WebSocketTests**: Tests the WebSocket functionality
   - WebSocket connection can be established
   - Messages can be sent and received
   - Asynchronous operations work correctly

### Frontend Tests

1. **Virtual Classroom WebSocket Connection**: Tests the WebSocket functionality
   - Connection establishes successfully
   - Reconnection logic works properly
   - Messages can be sent and received
   - Seat status updates are processed correctly
   - Error messages are displayed properly
   - Notification system works for different notification types

2. **Virtual Classroom UI Interaction**: Tests the user interface interaction
   - Raise hand button works and sends the correct API request
   - Share laptop button checks for a seat first
   - End turn button works and sends the correct API request

## Manual Testing Checklist

In addition to automated tests, here are some scenarios to test manually:

- [ ] A student can join the classroom and select a seat
- [ ] A student can raise their hand
- [ ] A teacher can see students who raised hands
- [ ] A teacher can call on a student
- [ ] A student can share their laptop content
- [ ] A teacher can start an update round
- [ ] The timer works properly during an update round
- [ ] Students can end their turns during update rounds
- [ ] Chat functionality works between users
- [ ] WebSocket reconnects after a connection loss
- [ ] All notifications display properly
- [ ] The classroom looks correct on different screen sizes
