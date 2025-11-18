import os  # MỚI: Thêm để đọc biến môi trường
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from flask_cors import CORS
from dateutil.parser import parse
from twilio.rest import Client  # MỚI: Thêm thư viện Twilio

# Import geocoding MIỄN PHÍ
from geocoding_free import geocode_address

# --- Khởi tạo và Cấu hình ---
app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blood.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cấu hình SQLite... (giữ nguyên)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'timeout': 30,
        'check_same_thread': False
    },
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# --- MODELS --- (Giữ nguyên)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default='')
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='donor')
    address = db.Column(db.String(200), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    blood_type = db.Column(db.String(5), nullable=True)
    last_donation = db.Column(db.Date, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'role': self.role,
            'address': self.address,
            'lat': self.lat,
            'lng': self.lng,
            'blood_type': self.blood_type,
            'last_donation': self.last_donation.isoformat() if self.last_donation else None
        }

class Hospital(db.Model):
    __tablename__ = 'hospitals'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)

    def to_dict(self):
         return {'id': self.id, 'name': self.name, 'lat': self.lat, 'lng': self.lng }


# --- CÁC API ROUTE --- (Giữ nguyên các route cũ)

@app.route('/')
def index():
    return jsonify({'message': 'Blood Donation API is running with FREE Geocoding!'})

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify({'count': len(users), 'users': [user.to_dict() for user in users]})

@app.route('/hospitals', methods=['GET'])
def get_hospitals():
    hospitals = Hospital.query.all()
    return jsonify({'count': len(hospitals), 'hospitals': [h.to_dict() for h in hospitals]})


@app.route('/register_donor', methods=['POST'])
def register_donor():
    data = request.get_json()
    # ... (code đăng ký giữ nguyên) ...
    required_fields = ['fullName', 'email', 'phone', 'password', 'address', 'bloodType']
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({'error': 'Thiếu thông tin bắt buộc hoặc thông tin rỗng'}), 400
    if User.query.filter((User.email == data['email']) | (User.phone == data['phone'])).first():
         return jsonify({'error': 'Email hoặc số điện thoại đã tồn tại'}), 409
    address = data['address']
    lat, lng = None, None
    try:
        coords = geocode_address(address)
        if coords:
            lat, lng = coords
            print(f"✅ Geocoding thành công cho '{address}'")
        else:
            print(f"⚠️ Không tìm thấy tọa độ cho '{address}'")
            print(f"💡 Người dùng vẫn được đăng ký, có thể cập nhật địa chỉ sau")
    except Exception as e:
        print(f"❌ Lỗi khi geocoding: {e}")
    last_donation_date = None
    if data.get('lastDonationDate'):
        date_str = data['lastDonationDate']
        if date_str:
            try:
                last_donation_date = parse(date_str).date()
            except (ValueError, TypeError) as e:
                 print(f"Lỗi parse ngày '{date_str}': {e}")
                 return jsonify({'error': 'Định dạng ngày hiến máu cuối không hợp lệ (cần YYYY-MM-DD)'}), 400
    new_user = User(
        name=data['fullName'],
        email=data['email'],
        phone=data['phone'],
        password=data['password'],
        role='donor',
        address=address,
        lat=lat,
        lng=lng,
        blood_type=data['bloodType'],
        last_donation=last_donation_date
    )
    try:
        db.session.add(new_user)
        db.session.commit()
        user_dict = new_user.to_dict()
        if lat is None or lng is None:
            return jsonify({
                'message': 'Đăng ký thành công',
                'warning': 'Không thể xác định vị trí chính xác. Vui lòng kiểm tra lại địa chỉ hoặc cập nhật sau.',
                'user': user_dict
            }), 201
        return jsonify({
            'message': 'Đăng ký thành công', 
            'user': user_dict
        }), 201
    except Exception as e:
        db.session.rollback()
        print(f"Lỗi database: {e}")
        return jsonify({'error': 'Lỗi máy chủ nội bộ khi đăng ký'}), 500

@app.route('/login', methods=['POST'])
def login():
    # ... (code login giữ nguyên) ...
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Thiếu email hoặc mật khẩu'}), 400
    user = User.query.filter_by(email=data['email']).first()
    if user and user.password == data['password']:
        user_data = user.to_dict()
        return jsonify({'message': 'Đăng nhập thành công', 'user': user_data}), 200
    else:
        return jsonify({'error': 'Email hoặc mật khẩu không chính xác'}), 401


@app.route('/create_alert', methods=['POST'])
def create_alert():
    # ... (code create_alert giữ nguyên) ...
    data = request.get_json()
    required_alert_fields = ['hospital_id', 'blood_type']
    if not all(k in data for k in required_alert_fields):
        return jsonify({'error': 'Thiếu hospital_id hoặc blood_type'}), 400
    hospital = Hospital.query.get(data['hospital_id'])
    if not hospital:
        return jsonify({'error': 'Không tìm thấy bệnh viện'}), 404
    blood_type_needed = data['blood_type']
    radius_km = data.get('radius_km', 10)
    suitable_users = User.query.filter(
        User.role == 'donor',
        User.lat.isnot(None),
        User.lng.isnot(None),
        User.blood_type == blood_type_needed
    ).all()
    try:
        from ai_filter import filter_nearby_users
        results = filter_nearby_users(hospital, suitable_users, radius_km)
        top_50_users = results[:50]
        return jsonify({
            'hospital': hospital.to_dict(),
            'blood_type_needed': blood_type_needed,
            'radius_km': radius_km,
            'total_matched': len(results),
            'top_50_users': [
                {'user': r['user'].to_dict(), 'distance_km': r['distance'], 'ai_score': r['ai_score']}
                for r in top_50_users
            ]
        })
    except ImportError:
        return jsonify({'error': "Không tìm thấy file ai_filter.py hoặc file có lỗi."}), 500
    except Exception as e:
        print(f"Lỗi trong quá trình lọc AI: {e}")
        return jsonify({'error': 'Lỗi máy chủ nội bộ khi lọc người dùng'}), 500


@app.route('/users/<int:user_id>', methods=['PUT', 'PATCH'])
def update_user_profile(user_id):
    # ... (code update_user_profile giữ nguyên) ...
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    allowed_fields = ['name', 'phone', 'address', 'blood_type', 'last_donation']
    geocoding_needed = False
    old_address = user.address
    for field in allowed_fields:
        if field in data:
            if field == 'last_donation':
                date_str = data[field]
                if date_str:
                    try:
                        setattr(user, field, parse(date_str).date())
                    except (ValueError, TypeError):
                        return jsonify({'error': f'Định dạng ngày {field} không hợp lệ'}), 400
                else:
                     setattr(user, field, None)
            else:
                 setattr(user, field, data[field])
            if field == 'address' and data[field] != old_address:
                geocoding_needed = True
    if geocoding_needed and user.address:
        print(f"\n🔄 ĐANG CẬP NHẬT TỌA ĐỘ")
        print(f"   Địa chỉ cũ: {old_address}")
        print(f"   Địa chỉ mới: {user.address}")
        try:
            coords = geocode_address(user.address)
            if coords:
                user.lat, user.lng = coords
                print(f"✅ Cập nhật tọa độ thành công!")
            else:
                user.lat = None
                user.lng = None
                print(f"⚠️ Không tìm thấy tọa độ cho địa chỉ mới")
        except Exception as e:
            print(f"❌ Lỗi khi geocode: {e}")
    try:
        db.session.commit()
        return jsonify({'message': 'Cập nhật thông tin thành công', 'user': user.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Lỗi khi cập nhật database: {e}")
        return jsonify({'error': 'Lỗi máy chủ nội bộ khi cập nhật'}), 500

# --- MỚI: ROUTE ĐỂ GỬI TIN NHẮN HÀNG LOẠT ---
@app.route('/notify_donors', methods=['POST'])
def notify_donors():
    data = request.get_json()
    donor_ids = data.get('donor_ids')
    message_body = data.get('message')

    if not donor_ids or not message_body:
        return jsonify({'error': 'Thiếu ID người hiến hoặc nội dung tin nhắn'}), 400

    # --- TÍCH HỢP TWILIO ---
    # Lấy thông tin từ biến môi trường (An toàn hơn là hardcode)
    # BẠN CẦN TỰ SET CÁC BIẾN NÀY TRONG TERMINAL CỦA BẠN
    # Ví dụ:
    # export TWILIO_ACCOUNT_SID='AC...'
    # export TWILIO_AUTH_TOKEN='...'
    # export TWILIO_PHONE_NUMBER='+1234567890'
    account_sid = os.environ.get('ACe5f6aea2c27b1364260fa0cb70894c01')
    auth_token = os.environ.get('f2be449d4da87bd833e03966bc305a77')
    twilio_phone = os.environ.get('+84935118290')

    if not account_sid or not auth_token or not twilio_phone:
        print("❌ LỖI: Chưa cấu hình biến môi trường TWILIO (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)")
        return jsonify({'error': 'Dịch vụ thông báo (SMS) chưa được cấu hình phía máy chủ.'}), 500

    try:
        client = Client(account_sid, auth_token)
        
        # Lấy SĐT của các user được chọn
        users_to_notify = User.query.filter(User.id.in_(donor_ids)).all()
        
        success_count = 0
        fail_count = 0
        
        print(f"📣 Bắt đầu gửi {len(users_to_notify)} thông báo...")

        for user in users_to_notify:
            if user.phone: # Chỉ gửi nếu có SĐT
                try:
                    # TODO: Chuyển đổi SĐT sang định dạng E.164 (ví dụ: 090... -> +8490...)
                    # Tạm giả định SĐT đã đúng định dạng
                    phone_number = user.phone
                    if phone_number.startswith('0'):
                        phone_number = '+84' + phone_number[1:]

                    message = client.messages.create(
                        body=message_body,
                        from_=twilio_phone,
                        to=phone_number
                    )
                    print(f"✅ Đã gửi SMS đến {user.name} (SID: {message.sid})")
                    success_count += 1
                except Exception as e:
                    print(f"⚠️ Lỗi khi gửi SMS đến {user.name} (SĐT: {user.phone}): {e}")
                    fail_count += 1
            else:
                print(f"⚠️ Bỏ qua {user.name} do không có SĐT.")
                fail_count += 1

        return jsonify({
            'message': f'Hoàn tất gửi thông báo: {success_count} thành công, {fail_count} thất bại.'
        }), 200

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng từ Twilio: {e}")
        return jsonify({'error': f'Lỗi dịch vụ gửi tin nhắn: {e}'}), 500


# --- CHẠY ỨNG DỤNG ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)