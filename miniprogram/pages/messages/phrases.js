module.exports = [
  { id: 'shopping', name: '购物付款', icon: '🛍️', items: [
    ['how-much', '这个多少钱？', 'Cái này bao nhiêu tiền?'],
    ['try-it', '我可以试一下吗？', 'Tôi có thể thử không?'],
    ['discount', '可以便宜一点吗？', 'Có thể giảm giá một chút không?'],
    ['qr-payment', '可以扫码付款吗？', 'Có thể thanh toán bằng mã QR không?'],
    ['invoice', '请给我发票。', 'Vui lòng cho tôi hóa đơn.']
  ]},
  { id: 'greetings', name: '问候交流', icon: '👋', items: [
    ['hello', '你好！', 'Xin chào!'],
    ['nice-meet', '很高兴认识您。', 'Rất vui được gặp anh/chị.'],
    ['thank-you', '谢谢您的帮助。', 'Cảm ơn sự giúp đỡ của anh/chị.'],
    ['sorry', '对不起，打扰了。', 'Xin lỗi vì đã làm phiền.'],
    ['dont-understand', '我没听懂，请再说一遍。', 'Tôi chưa hiểu, vui lòng nói lại một lần nữa.']
  ]},
  { id: 'business', name: '商务沟通', icon: '💼', items: [
    ['discuss-cooperation', '我们想讨论合作方案。', 'Chúng tôi muốn thảo luận về phương án hợp tác.'],
    ['send-quotation', '请把详细报价发给我。', 'Vui lòng gửi báo giá chi tiết cho tôi.'],
    ['minimum-order', '最小起订量是多少？', 'Số lượng đặt hàng tối thiểu là bao nhiêu?'],
    ['sign-contract', '我们什么时候可以签合同？', 'Khi nào chúng ta có thể ký hợp đồng?'],
    ['contact-later', '我们稍后再联系。', 'Chúng ta sẽ liên hệ lại sau.']
  ]},
  { id: 'factory', name: '工厂考察', icon: '🏭', items: [
    ['visit-factory', '我们想参观工厂。', 'Chúng tôi muốn tham quan nhà máy.'],
    ['production-process', '请介绍一下生产流程。', 'Vui lòng giới thiệu quy trình sản xuất.'],
    ['monthly-capacity', '每月产能是多少？', 'Công suất mỗi tháng là bao nhiêu?'],
    ['quality-check', '如何进行质量检验？', 'Việc kiểm tra chất lượng được thực hiện như thế nào?'],
    ['delivery-time', '交货期需要多久？', 'Thời gian giao hàng là bao lâu?']
  ]},
  { id: 'transport', name: '交通出行', icon: '🚕', items: [
    ['to-airport', '请带我去机场。', 'Vui lòng đưa tôi đến sân bay.'],
    ['city-distance', '这里离市中心多远？', 'Từ đây đến trung tâm thành phố bao xa?'],
    ['stop-here', '请在这里停车。', 'Vui lòng dừng xe ở đây.'],
    ['fare', '车费多少钱？', 'Tiền xe là bao nhiêu?'],
    ['lost', '我迷路了，请帮帮我。', 'Tôi bị lạc đường, xin hãy giúp tôi.']
  ]},
  { id: 'hotel', name: '酒店住宿', icon: '🏨', items: [
    ['room-booked', '我已经预订了房间。', 'Tôi đã đặt phòng rồi.'],
    ['check-in', '我想办理入住。', 'Tôi muốn làm thủ tục nhận phòng.'],
    ['wifi-password', 'Wi-Fi密码是什么？', 'Mật khẩu Wi-Fi là gì?'],
    ['check-out', '我想办理退房。', 'Tôi muốn làm thủ tục trả phòng.'],
    ['keep-luggage', '请帮我保管行李。', 'Vui lòng giữ hành lý giúp tôi.']
  ]},
  { id: 'dining', name: '餐饮点餐', icon: '🍜', items: [
    ['menu', '请给我看一下菜单。', 'Vui lòng cho tôi xem thực đơn.'],
    ['not-spicy', '请不要放辣。', 'Vui lòng không cho cay.'],
    ['seafood-allergy', '我对海鲜过敏。', 'Tôi bị dị ứng với hải sản.'],
    ['pay-bill', '请结账。', 'Vui lòng tính tiền.'],
    ['delicious', '很好吃，谢谢！', 'Rất ngon, cảm ơn!']
  ]},
  { id: 'emergency', name: '医疗求助', icon: '🆘', items: [
    ['not-well', '我不舒服。', 'Tôi cảm thấy không khỏe.'],
    ['need-doctor', '我需要看医生。', 'Tôi cần gặp bác sĩ.'],
    ['nearest-hospital', '最近的医院在哪里？', 'Bệnh viện gần nhất ở đâu?'],
    ['call-ambulance', '请叫救护车。', 'Vui lòng gọi xe cấp cứu.'],
    ['lost-passport', '我的护照丢了。', 'Tôi bị mất hộ chiếu.']
  ]}
].map((scene) => ({
  id: scene.id,
  name: scene.name,
  icon: scene.icon,
  items: scene.items.map(([id, zh, vi]) => ({ id, zh, vi }))
}));
