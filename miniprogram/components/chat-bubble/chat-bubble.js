// components/chat-bubble/chat-bubble.js
Component({
  properties: {
    text: { type: String, value: '' },
    side: { type: String, value: 'left' }, // left | right
    isSource: { type: Boolean, value: false }
  }
});