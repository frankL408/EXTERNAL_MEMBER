from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4, letter, inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.pdfgen import canvas
from flask_migrate import Migrate
from PIL import Image as PILImage
import os
from datetime import datetime, timedelta
import io
import random
import traceback
import base64
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ZCAS University Colors
ZCAS_COLORS = {
    'primary': '#1E3A8A',
    'secondary': '#DC2626',
    'accent': '#059669',
    'light': '#EFF6FF',
    'dark': '#1E3A8A'
}

# ZCAS University Contact Information
ZCAS_CONTACT = {
    'phone': '+260211222508',
    'email': 'library@zcasu.edu.zm',
    'address': 'ZCAS University Library, Lusaka, Zambia',
    'property_notice': 'THIS CARD REMAINS THE PROPERTY OF ZCAS UNIVERSITY',
    'website': 'www.zcasu.edu.zm'
}

# Fee Structure
FEE_STRUCTURE = {
    'id_card': 100,
    'wifi': 120,
    'monthly': 90,
    'six_months': 500
}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Database Models


class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    nrc_number = db.Column(db.String(50), nullable=False)
    nationality = db.Column(db.String(50), default='Zambian')
    membership_type = db.Column(db.String(20), nullable=False)
    duration_months = db.Column(db.Integer, default=1)
    photo_path = db.Column(db.String(200), nullable=True)
    receipt_number = db.Column(db.String(50), nullable=True)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='active')
    rfid_uid = db.Column(db.String(50), unique=True, nullable=True)

    payments = db.relationship('Payment', backref='member', lazy=True)
    access_logs = db.relationship('AccessLog', backref='member', lazy=True)
    current_session = db.relationship(
        'CurrentSession', backref='member', uselist=False)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey(
        'member.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), default='Cash')
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    received_by = db.Column(db.String(80), nullable=False)
    fee_breakdown = db.Column(db.Text, nullable=True)

    def set_fee_breakdown(self, breakdown_dict):
        self.fee_breakdown = json.dumps(breakdown_dict)

    def get_fee_breakdown(self):
        if self.fee_breakdown:
            return json.loads(self.fee_breakdown)
        return {}


class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey(
        'member.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='success')
    message = db.Column(db.String(200), nullable=True)


class CurrentSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey(
        'member.id'), nullable=False, unique=True)
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


def init_database():
    try:
        with app.app_context():
            db.create_all()
            print("✅ Database tables checked/created successfully")

            if not Admin.query.first():
                admin = Admin(username='admin')
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("✅ Admin user created (username: admin, password: admin123)")
            else:
                print("✅ Admin user already exists")

            return True
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False


# Utility Functions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_member_id():
    total_members = Member.query.count()
    new_id = 2025001 + total_members
    return f"EXT{new_id}"


def generate_receipt_number():
    timestamp = datetime.now().strftime("%y%m%d")
    random_num = random.randint(1000, 9999)
    return f"ZCAS-RCPT-{timestamp}-{random_num}"


# ========== CORE ROUTES ==========

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        total_members = Member.query.count()
        active_members = Member.query.filter(Member.status == 'active').count()
        expired_members = Member.query.filter(
            Member.status == 'expired').count()
        current_in_library = CurrentSession.query.count()

        return render_template('dashboard.html',
                               total_members=total_members,
                               active_members=active_members,
                               expired_members=expired_members,
                               current_in_library=current_in_library)
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        return render_template('dashboard.html', total_members=0, active_members=0,
                               expired_members=0, current_in_library=0)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):
            login_user(admin)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))


@app.route('/scan_member', methods=['GET'])
@login_required
def scan_member():
    return render_template('scan_member.html')


# ========== RFID SCANNING API ENDPOINTS ==========

@app.route('/api/scan_rfid', methods=['POST'])
def api_scan_rfid():
    """Process RFID scan for check-in/out"""
    try:
        data = request.get_json()
        scanned_id = data.get('rfid_uid', '').strip()

        if not scanned_id:
            return jsonify({
                'success': False,
                'message': 'Please scan a valid RFID card'
            }), 400

        # Find member by RFID UID or Member ID
        member = Member.query.filter_by(rfid_uid=scanned_id).first()
        if not member:
            member = Member.query.filter_by(member_id=scanned_id).first()

        if not member:
            return jsonify({
                'success': False,
                'message': f'No member found with ID: {scanned_id}'
            }), 404

        # Check membership expiry
        today = datetime.utcnow().date()
        is_expired = False
        days_remaining = None

        if member.expiry_date:
            expiry_date = member.expiry_date.date()
            days_remaining = (expiry_date - today).days
            is_expired = days_remaining < 0

            if is_expired and member.status == 'active':
                member.status = 'expired'
                db.session.commit()

        # Block expired members
        if is_expired:
            log = AccessLog(
                member_id=member.id,
                action='check_in',
                status='denied',
                message=f'Access denied - Membership expired on {member.expiry_date.strftime("%Y-%m-%d")}'
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({
                'success': False,
                'is_expired': True,
                'member_id': member.member_id,
                'full_name': member.full_name,
                'message': 'ACCESS DENIED: Your membership has expired. Please renew.',
                'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None
            }), 403

        # Check current session
        current_session = CurrentSession.query.filter_by(
            member_id=member.id).first()

        if current_session:
            # Check out
            check_out_time = datetime.utcnow()
            duration_minutes = int(
                (check_out_time - current_session.check_in_time).total_seconds() / 60)

            log = AccessLog(
                member_id=member.id,
                action='check_out',
                status='success',
                message=f'Checked out after {duration_minutes} minutes'
            )
            db.session.add(log)
            db.session.delete(current_session)
            db.session.commit()

            return jsonify({
                'success': True,
                'action': 'check_out',
                'member_id': member.member_id,
                'full_name': member.full_name,
                'message': f'Goodbye {member.full_name}! Checked out successfully.',
                'duration_minutes': duration_minutes
            })
        else:
            # Check in
            new_session = CurrentSession(member_id=member.id)
            db.session.add(new_session)

            log = AccessLog(
                member_id=member.id,
                action='check_in',
                status='success',
                message='Checked in successfully'
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({
                'success': True,
                'action': 'check_in',
                'member_id': member.member_id,
                'full_name': member.full_name,
                'message': f'Welcome {member.full_name}! Checked in successfully.',
                'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None,
                'days_remaining': days_remaining
            })

    except Exception as e:
        print(f"Error in scan_rfid: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error processing scan: {str(e)}'
        }), 500


@app.route('/api/check_rfid/<rfid_uid>')
def api_check_rfid(rfid_uid):
    """Check if RFID card is already assigned to a member"""
    try:
        member = Member.query.filter_by(rfid_uid=rfid_uid).first()
        if member:
            return jsonify({
                'assigned': True,
                'member_id': member.member_id,
                'member_name': member.full_name
            })
        return jsonify({'assigned': False})
    except Exception as e:
        return jsonify({'assigned': False, 'error': str(e)}), 500


@app.route('/api/assign_rfid_to_member', methods=['POST'])
@login_required
def api_assign_rfid_to_member():
    """Assign RFID card to a member"""
    try:
        data = request.get_json()
        member_id = data.get('member_id')
        rfid_uid = data.get('rfid_uid')

        if not member_id or not rfid_uid:
            return jsonify({'success': False, 'message': 'Missing member ID or RFID UID'}), 400

        # Check if RFID is already assigned
        existing = Member.query.filter_by(rfid_uid=rfid_uid).first()
        if existing and existing.id != member_id:
            return jsonify({'success': False, 'message': f'RFID already assigned to {existing.full_name}'}), 400

        member = Member.query.get(member_id)
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'}), 404

        member.rfid_uid = rfid_uid
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'RFID assigned successfully',
            'member_name': member.full_name,
            'member_id': member.member_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/search_members')
@login_required
def api_search_members():
    """Search members by name, ID, or NRC"""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'success': True, 'members': []})

        members = Member.query.filter(
            db.or_(
                Member.full_name.ilike(f'%{query}%'),
                Member.member_id.ilike(f'%{query}%'),
                Member.nrc_number.ilike(f'%{query}%')
            )
        ).limit(20).all()

        members_data = []
        for member in members:
            members_data.append({
                'id': member.id,
                'member_id': member.member_id,
                'full_name': member.full_name,
                'nrc_number': member.nrc_number,
                'rfid_assigned': bool(member.rfid_uid)
            })

        return jsonify({'success': True, 'members': members_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/current_members')
@login_required
def api_current_members():
    """Get all members currently in the library"""
    try:
        sessions = CurrentSession.query.all()
        members_in_library = []

        for session in sessions:
            member = session.member
            members_in_library.append({
                'member_id': member.member_id,
                'full_name': member.full_name,
                'photo_path': member.photo_path,
                'check_in_time': session.check_in_time.strftime('%Y-%m-%d %I:%M %p'),
                'duration_minutes': int((datetime.utcnow() - session.check_in_time).total_seconds() / 60)
            })

        return jsonify({
            'success': True,
            'count': len(members_in_library),
            'members': members_in_library
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/access_logs')
@login_required
def api_access_logs():
    """Get access logs with filtering"""
    try:
        status = request.args.get('status', 'all')
        user_query = request.args.get('user', '').strip()
        card_id = request.args.get('card_id', '').strip()
        date_from_str = request.args.get('date_from', '')
        date_to_str = request.args.get('date_to', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        query = db.session.query(AccessLog, Member).join(
            Member, AccessLog.member_id == Member.id)

        if status != 'all' and status in ['check_in', 'check_out']:
            query = query.filter(AccessLog.action == status)

        if user_query:
            query = query.filter(
                db.or_(
                    Member.full_name.ilike(f'%{user_query}%'),
                    Member.member_id.ilike(f'%{user_query}%')
                )
            )

        if card_id:
            query = query.filter(Member.rfid_uid.ilike(f'%{card_id}%'))

        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
                query = query.filter(AccessLog.timestamp >= date_from)
            except ValueError:
                pass

        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
                date_to = date_to.replace(hour=23, minute=59, second=59)
                query = query.filter(AccessLog.timestamp <= date_to)
            except ValueError:
                pass

        total_logs = query.count()
        check_ins = query.filter(AccessLog.action == 'check_in').count()
        check_outs = query.filter(AccessLog.action == 'check_out').count()

        query = query.order_by(AccessLog.timestamp.desc())
        paginated = query.offset((page - 1) * per_page).limit(per_page).all()

        logs_data = []
        for access_log, member in paginated:
            logs_data.append({
                'id': access_log.id,
                'member_id': member.member_id,
                'member_name': member.full_name,
                'card_id': member.rfid_uid or 'Not Assigned',
                'action': access_log.action,
                'status': access_log.status,
                'message': access_log.message,
                'timestamp': access_log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p')
            })

        return jsonify({
            'success': True,
            'logs': logs_data,
            'summary': {
                'total': total_logs,
                'check_ins': check_ins,
                'check_outs': check_outs
            },
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_logs
            }
        })
    except Exception as e:
        print(f"Error in api_access_logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/members')
@login_required
def view_members():
    try:
        members = Member.query.order_by(Member.registration_date.desc()).all()
        return render_template('members.html', members=members)
    except Exception as e:
        flash(f'Error loading members: {str(e)}', 'error')
        return render_template('members.html', members=[])


@app.route('/auto_check_expiry')
@login_required
def auto_check_expiry():
    try:
        members = Member.query.filter(Member.status == 'active').all()
        updated_count = 0
        today = datetime.utcnow().date()

        for member in members:
            if member.expiry_date:
                expiry_date = member.expiry_date.date()
                if expiry_date < today:
                    member.status = 'expired'
                    updated_count += 1

        if updated_count > 0:
            db.session.commit()
            flash(
                f'Updated {updated_count} members to expired status', 'warning')
        else:
            flash('No expired members found', 'info')
    except Exception as e:
        flash(f'Error checking expiry: {str(e)}', 'error')

    return redirect(url_for('view_members'))


# ========== MEMBER MANAGEMENT ROUTES ==========

@app.route('/register_member', methods=['GET', 'POST'])
@login_required
def register_member():
    if request.method == 'GET':
        return render_template('register_member.html')

    elif request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            address = request.form.get('address', '').strip()
            nrc_number = request.form.get('nrc_number', '').strip()
            membership_type = request.form.get('membership_type')

            if not all([full_name, email, phone, address, nrc_number, membership_type]):
                flash('Please fill in all required fields', 'error')
                return render_template('register_member.html')

            member_id = generate_member_id()
            registration_date = datetime.utcnow()

            member = Member(
                member_id=member_id,
                full_name=full_name,
                email=email,
                phone=phone,
                address=address,
                nrc_number=nrc_number,
                membership_type=membership_type,
                registration_date=registration_date,
                status='active'
            )

            if membership_type == 'monthly':
                member.expiry_date = registration_date + timedelta(days=30)
            else:
                member.expiry_date = registration_date + timedelta(days=180)

            db.session.add(member)
            db.session.commit()

            flash(
                f'Member registered successfully! Member ID: {member.member_id}', 'success')
            return redirect(url_for('view_members'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error registering member: {str(e)}', 'error')
            return render_template('register_member.html')


# Initialize database when app starts
print("🚀 Starting application...")
init_database()

if __name__ == '__main__':
    print("🌐 Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
