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
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max file size

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

# CORRECTED FEE STRUCTURE - NORMAL FEES AS SPECIFIED
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
    """Initialize database - Safely creates tables and admin user without dropping existing data"""
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

            total_members = Member.query.count()
            total_payments = Payment.query.count()
            print(
                f"📊 Current data: {total_members} members, {total_payments} payments")

            print("✅ Database initialization completed successfully")
            return True

    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        print(traceback.format_exc())
        return False


# Utility Functions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image(image_path, output_size=(150, 150)):
    try:
        with PILImage.open(image_path) as img:
            img = img.resize(output_size, PILImage.Resampling.LANCZOS)
            img.save(image_path)
            print(f"✅ Image resized and saved to: {image_path}")
    except Exception as e:
        print(f"❌ Error resizing image: {e}")


def generate_member_id():
    total_members = Member.query.count()
    new_id = 2025001 + total_members
    return f"EXT{new_id}"


def generate_receipt_number():
    timestamp = datetime.now().strftime("%y%m%d")
    random_num = random.randint(1000, 9999)
    return f"ZCAS-RCPT-{timestamp}-{random_num}"


def calculate_total_fees(membership_type, duration_months=1):
    print(
        f"💰 Calculating fees for: {membership_type}, duration: {duration_months} months")

    if membership_type == 'monthly':
        membership_fee = FEE_STRUCTURE['monthly'] * duration_months
    elif membership_type == 'six_months':
        membership_fee = FEE_STRUCTURE['six_months']
        duration_months = 6
    else:
        membership_fee = 0

    id_card_fee = FEE_STRUCTURE['id_card']
    wifi_fee = FEE_STRUCTURE['wifi']

    total = membership_fee + id_card_fee + wifi_fee

    return {
        'membership_fee': membership_fee,
        'id_card_fee': id_card_fee,
        'wifi_fee': wifi_fee,
        'total': total,
        'duration_months': duration_months
    }


def calculate_renewal_fees(membership_type, duration_months=1):
    if membership_type == 'monthly':
        return FEE_STRUCTURE['monthly'] * duration_months
    elif membership_type == 'six_months':
        return FEE_STRUCTURE['six_months']
    else:
        return 0


@app.context_processor
def inject_template_vars():
    logo_exists = (
        os.path.exists('static/images/logo.png') or
        os.path.exists('static/uploads/logo.png') or
        os.path.exists('images/logo.png') or
        os.path.exists('logo.png')
    )
    return {
        'now': datetime.utcnow(),
        'colors': ZCAS_COLORS,
        'fee_structure': FEE_STRUCTURE,
        'contact_info': ZCAS_CONTACT,
        'logo_exists': logo_exists
    }


# ========== CORE ROUTES ==========

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')

        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):
            login_user(admin)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
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
        monthly_members = Member.query.filter_by(
            membership_type='monthly').count()
        six_months_members = Member.query.filter_by(
            membership_type='six_months').count()

        monthly_revenue = 0
        six_months_revenue = 0
        total_revenue = 0

        payments = Payment.query.all()
        for payment in payments:
            fee_breakdown = payment.get_fee_breakdown()
            if fee_breakdown.get('membership_type') == 'monthly':
                monthly_revenue += payment.amount
            elif fee_breakdown.get('membership_type') == 'six_months':
                six_months_revenue += payment.amount
            total_revenue += payment.amount

        members = Member.query.order_by(Member.registration_date.desc()).all()
        logo_exists = os.path.exists('static/images/logo.png')

        return render_template('dashboard.html',
                               total_members=total_members,
                               active_members=active_members,
                               expired_members=expired_members,
                               current_in_library=current_in_library,
                               monthly_members=monthly_members,
                               six_months_members=six_months_members,
                               monthly_revenue=monthly_revenue,
                               six_months_revenue=six_months_revenue,
                               total_revenue=total_revenue,
                               members=members,
                               logo_exists=logo_exists)
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('dashboard.html',
                               total_members=0, active_members=0, expired_members=0,
                               current_in_library=0, monthly_members=0, six_months_members=0,
                               monthly_revenue=0, six_months_revenue=0, total_revenue=0,
                               members=[], logo_exists=False)


@app.route('/calendar')
@login_required
def calendar_view():
    try:
        members = Member.query.all()
        calendar_events = []
        upcoming_events = []
        today_date = datetime.utcnow().date()

        for member in members:
            if member.registration_date:
                registration_date = member.registration_date.date() if hasattr(
                    member.registration_date, 'date') else member.registration_date
                calendar_events.append({
                    'id': f'reg_{member.id}',
                    'title': f'Registration: {member.full_name}',
                    'start': registration_date.strftime('%Y-%m-%d'),
                    'color': '#1E3A8A',
                    'type': 'registration',
                    'member_id': member.member_id,
                    'description': f'New member registration: {member.full_name}',
                    'action_url': url_for('member_details', member_id=member.id)
                })

            if member.expiry_date:
                expiry_date = member.expiry_date.date() if hasattr(
                    member.expiry_date, 'date') else member.expiry_date
                days_until_expiry = (expiry_date - today_date).days
                color = '#DC2626' if days_until_expiry < 0 else '#F59E0B'

                calendar_events.append({
                    'id': f'exp_{member.id}',
                    'title': f'Expiry: {member.full_name}',
                    'start': expiry_date.strftime('%Y-%m-%d'),
                    'color': color,
                    'type': 'expiry',
                    'member_id': member.member_id,
                    'description': f'Membership expiry for {member.full_name}',
                    'action_url': url_for('renew_member', member_id=member.id) if days_until_expiry < 0 else url_for('member_details', member_id=member.id)
                })

        upcoming_date = today_date + timedelta(days=30)

        for event in calendar_events:
            try:
                event_date = datetime.strptime(
                    event['start'], '%Y-%m-%d').date()
                if today_date <= event_date <= upcoming_date:
                    event_title = event['title'].split(
                        ': ')[-1] if ': ' in event['title'] else event['title']
                    upcoming_events.append({
                        'type': event.get('type', 'event'),
                        'title': event_title,
                        'date': event_date,
                        'member_id': event.get('member_id', 'N/A')
                    })
            except (ValueError, TypeError) as e:
                print(f"Error processing event date: {e}")
                continue

        upcoming_events.sort(key=lambda x: x['date'])
        upcoming_events = upcoming_events[:10]

    except Exception as e:
        print(f"Error loading calendar events: {e}")
        calendar_events = []
        upcoming_events = []

    return render_template('calendar.html',
                           calendar_events=calendar_events,
                           upcoming_events=upcoming_events)


@app.route('/api/calendar_events')
@login_required
def calendar_events_api():
    try:
        events = []
        members = Member.query.all()
        today_date = datetime.utcnow().date()

        for member in members:
            if member.registration_date:
                registration_date = member.registration_date.date() if hasattr(
                    member.registration_date, 'date') else member.registration_date
                events.append({
                    'id': f'reg_{member.id}',
                    'title': f'Registration: {member.full_name}',
                    'start': registration_date.isoformat(),
                    'color': '#1E3A8A',
                    'extendedProps': {
                        'type': 'registration',
                        'member_id': member.member_id,
                        'description': f'New member registration: {member.full_name}',
                        'action_url': url_for('member_details', member_id=member.id)
                    }
                })

            if member.expiry_date:
                expiry_date = member.expiry_date.date() if hasattr(
                    member.expiry_date, 'date') else member.expiry_date
                days_until_expiry = (expiry_date - today_date).days
                color = '#DC2626' if days_until_expiry < 0 else '#F59E0B'

                events.append({
                    'id': f'exp_{member.id}',
                    'title': f'Expiry: {member.full_name}',
                    'start': expiry_date.isoformat(),
                    'color': color,
                    'extendedProps': {
                        'type': 'expiry',
                        'member_id': member.member_id,
                        'description': f'Membership expiry for {member.full_name}',
                        'action_url': url_for('renew_member', member_id=member.id) if days_until_expiry < 0 else url_for('member_details', member_id=member.id)
                    }
                })

        return jsonify(events)
    except Exception as e:
        print(f"Error in calendar_events_api: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/register_member', methods=['GET', 'POST'])
@login_required
def register_member():
    if request.method == 'GET':
        selected_date = request.args.get('date')
        if selected_date:
            try:
                registration_date = datetime.strptime(
                    selected_date, '%Y-%m-%d')
            except:
                registration_date = datetime.utcnow()
        else:
            registration_date = datetime.utcnow()

        return render_template('register_member.html',
                               registration_date=registration_date.strftime('%Y-%m-%d'))

    elif request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            address = request.form.get('address', '').strip()
            nrc_number = request.form.get('nrc_number', '').strip()
            nationality = request.form.get('nationality', 'Zambian')
            membership_type = request.form.get('membership_type')
            duration_months = request.form.get('duration_months', '1')
            payment_method = request.form.get('payment_method', 'Cash')
            registration_date_str = request.form.get('registration_date', '')

            required_fields = {
                'full_name': full_name,
                'email': email,
                'phone': phone,
                'address': address,
                'nrc_number': nrc_number,
                'membership_type': membership_type
            }

            missing_fields = [field for field,
                              value in required_fields.items() if not value]
            if missing_fields:
                flash(
                    f'Please fill in all required fields. Missing: {", ".join(missing_fields)}', 'error')
                return render_template('register_member.html')

            if registration_date_str:
                try:
                    registration_date = datetime.strptime(
                        registration_date_str, '%Y-%m-%d')
                except ValueError:
                    registration_date = datetime.utcnow()
            else:
                registration_date = datetime.utcnow()

            try:
                duration_months = int(duration_months)
                if duration_months < 1:
                    duration_months = 1
                elif duration_months > 12:
                    duration_months = 12
            except (ValueError, TypeError):
                duration_months = 1

            photo_file = request.files.get('photo')
            photo_filename = None

            if photo_file and photo_file.filename:
                if allowed_file(photo_file.filename):
                    filename = secure_filename(photo_file.filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    photo_filename = f"{timestamp}_{filename}"
                    photo_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], photo_filename)

                    os.makedirs(os.path.dirname(photo_path), exist_ok=True)
                    photo_file.save(photo_path)

                    try:
                        resize_image(photo_path, output_size=(120, 150))
                    except Exception as resize_error:
                        print(f"⚠️ Could not resize image: {resize_error}")
                else:
                    flash(
                        'Invalid file type. Please upload JPG or PNG images only.', 'error')
                    return render_template('register_member.html')
            else:
                flash('Please upload a profile photo', 'error')
                return render_template('register_member.html')

            receipt_number = generate_receipt_number()
            member_id = generate_member_id()
            fees = calculate_total_fees(membership_type, duration_months)

            member = Member(
                member_id=member_id,
                full_name=full_name,
                email=email,
                phone=phone,
                address=address,
                nrc_number=nrc_number,
                nationality=nationality,
                membership_type=membership_type,
                duration_months=fees['duration_months'],
                photo_path=photo_filename,
                receipt_number=receipt_number,
                registration_date=registration_date,
                status='active'
            )

            if membership_type == 'monthly':
                member.expiry_date = registration_date + \
                    timedelta(days=30 * fees['duration_months'])
            else:
                member.expiry_date = registration_date + timedelta(days=180)

            db.session.add(member)
            db.session.flush()

            payment = Payment(
                receipt_number=receipt_number,
                member_id=member.id,
                amount=fees['total'],
                payment_method=payment_method,
                received_by=current_user.username,
                payment_date=registration_date
            )

            payment.set_fee_breakdown({
                'membership_fee': fees['membership_fee'],
                'id_card_fee': fees['id_card_fee'],
                'wifi_fee': fees['wifi_fee'],
                'duration_months': fees['duration_months'],
                'membership_type': membership_type,
                'is_renewal': False
            })

            db.session.add(payment)
            db.session.commit()

            duration_text = f"{fees['duration_months']} month(s)" if membership_type == 'monthly' else "6 months"
            flash(
                f'External Member registered successfully! Member ID: {member.member_id}. NRC: {nrc_number}. Duration: {duration_text}. Total Fees: K{fees["total"]}', 'success')
            return redirect(url_for('view_members'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ REGISTRATION FAILED: {e}")
            traceback.print_exc()
            flash(f'Error registering member: {str(e)}', 'error')
            return render_template('register_member.html')


@app.route('/members')
@login_required
def view_members():
    try:
        members = Member.query.order_by(Member.registration_date.desc()).all()

        today = datetime.utcnow().date()
        for member in members:
            if member.expiry_date:
                if hasattr(member.expiry_date, 'date'):
                    expiry_date = member.expiry_date.date()
                else:
                    expiry_date = member.expiry_date
                member.days_left = (expiry_date - today).days
            else:
                member.days_left = None

        active_members_count = len(
            [m for m in members if m.status == 'active'])
        expired_members_count = len(
            [m for m in members if m.status == 'expired'])

        monthly_members = Member.query.filter_by(
            membership_type='monthly').count()
        six_months_members = Member.query.filter_by(
            membership_type='six_months').count()

        expiring_soon_count = len([
            m for m in members
            if m.status == 'active' and m.expiry_date and
            m.days_left is not None and m.days_left <= 7 and m.days_left >= 0
        ])

        return render_template('members.html',
                               members=members,
                               active_members_count=active_members_count,
                               expired_members_count=expired_members_count,
                               monthly_members=monthly_members,
                               six_months_members=six_months_members,
                               expiring_soon_count=expiring_soon_count)
    except Exception as e:
        print(f"❌ Error loading members: {e}")
        flash(f'Error loading members: {str(e)}', 'error')
        return render_template('members.html', members=[], active_members_count=0,
                               expired_members_count=0, monthly_members=0,
                               six_months_members=0, expiring_soon_count=0)


@app.route('/renew_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
def renew_member(member_id):
    member = Member.query.get_or_404(member_id)

    if request.method == 'GET':
        return render_template('renew_member.html', member=member)

    elif request.method == 'POST':
        try:
            renew_period = request.form.get('renew_period', 'monthly')
            duration_months = request.form.get('duration_months', '1')
            payment_method = request.form.get('payment_method', 'Cash')
            renewal_date_str = request.form.get('renewal_date', '')

            if renewal_date_str:
                try:
                    renewal_date = datetime.strptime(
                        renewal_date_str, '%Y-%m-%d')
                except ValueError:
                    renewal_date = datetime.utcnow()
            else:
                renewal_date = datetime.utcnow()

            try:
                duration_months = int(duration_months)
                if duration_months < 1:
                    duration_months = 1
                elif duration_months > 12:
                    duration_months = 12
            except (ValueError, TypeError):
                duration_months = 1

            renewal_fee = calculate_renewal_fees(renew_period, duration_months)

            start_date = renewal_date
            if renew_period == 'monthly':
                new_expiry = start_date + timedelta(days=30 * duration_months)
            else:
                new_expiry = start_date + timedelta(days=180)

            member.expiry_date = new_expiry
            member.status = 'active'
            member.duration_months = duration_months if renew_period == 'monthly' else 6
            member.membership_type = renew_period

            receipt_number = generate_receipt_number()
            payment = Payment(
                receipt_number=receipt_number,
                member_id=member.id,
                amount=renewal_fee,
                payment_method=payment_method,
                received_by=current_user.username,
                payment_date=renewal_date
            )

            payment.set_fee_breakdown({
                'membership_fee': renewal_fee,
                'id_card_fee': 0,
                'wifi_fee': 0,
                'duration_months': duration_months if renew_period == 'monthly' else 6,
                'is_renewal': True,
                'membership_type': renew_period
            })

            db.session.add(payment)
            db.session.commit()

            duration_text = f"{duration_months} month(s)" if renew_period == 'monthly' else "6 months"
            flash(
                f'Member {member.full_name} renewed successfully for {duration_text}! Renewal fee: K{renewal_fee}', 'success')

        except Exception as e:
            db.session.rollback()
            print(f"Error renewing member: {e}")
            flash(f'Error renewing member: {str(e)}', 'error')

        return redirect(url_for('view_members'))


@app.route('/auto_check_expiry')
@login_required
def auto_check_expiry():
    try:
        members = Member.query.all()
        updated_count = 0
        today = datetime.utcnow().date()

        for member in members:
            if not member.expiry_date or member.status != 'active':
                continue

            try:
                expiry_date = member.expiry_date
                if hasattr(expiry_date, 'date'):
                    expiry_date = expiry_date.date()

                if expiry_date < today:
                    member.status = 'expired'
                    updated_count += 1
            except (TypeError, AttributeError):
                continue

        if updated_count > 0:
            db.session.commit()
            flash(
                f'Updated {updated_count} members to expired status', 'warning')
        else:
            flash('No expired members found', 'info')

    except Exception as e:
        flash(f'Error checking expiry: {str(e)}', 'error')

    return redirect(url_for('view_members'))


@app.route('/membership_calendar')
@login_required
def membership_calendar():
    return redirect(url_for('calendar_view'))


@app.route('/delete_member/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    try:
        member = Member.query.get_or_404(member_id)

        Payment.query.filter_by(member_id=member_id).delete()
        AccessLog.query.filter_by(member_id=member_id).delete()
        CurrentSession.query.filter_by(member_id=member_id).delete()

        if member.photo_path:
            photo_path = os.path.join(
                app.config['UPLOAD_FOLDER'], member.photo_path)
            if os.path.exists(photo_path):
                os.remove(photo_path)

        db.session.delete(member)
        db.session.commit()

        flash(
            f'Member {member.full_name} has been deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting member: {e}")
        flash(f'Error deleting member: {str(e)}', 'error')

    return redirect(url_for('view_members'))


@app.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete():
    try:
        member_ids = request.form.getlist('member_ids')

        if not member_ids:
            flash('No members selected for deletion', 'error')
            return redirect(url_for('view_members'))

        deleted_count = 0
        for member_id in member_ids:
            member = Member.query.get(member_id)
            if member:
                Payment.query.filter_by(member_id=member_id).delete()
                AccessLog.query.filter_by(member_id=member_id).delete()
                CurrentSession.query.filter_by(member_id=member_id).delete()

                if member.photo_path:
                    photo_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], member.photo_path)
                    if os.path.exists(photo_path):
                        os.remove(photo_path)

                db.session.delete(member)
                deleted_count += 1

        if deleted_count > 0:
            db.session.commit()
            flash(f'Successfully deleted {deleted_count} members', 'success')
        else:
            flash('No members were deleted', 'error')

    except Exception as e:
        db.session.rollback()
        print(f"Error during bulk deletion: {e}")
        flash(f'Error during bulk deletion: {str(e)}', 'error')

    return redirect(url_for('view_members'))


@app.route('/bulk_renew', methods=['POST'])
@login_required
def bulk_renew():
    try:
        member_ids = request.form.getlist('member_ids')
        renew_period = request.form.get('renew_period', 'monthly')
        duration_months = request.form.get('duration_months', '1')

        if not member_ids:
            flash('No members selected for renewal', 'error')
            return redirect(url_for('view_members'))

        try:
            duration_months = int(duration_months)
            if duration_months < 1:
                duration_months = 1
            elif duration_months > 12:
                duration_months = 12
        except (ValueError, TypeError):
            duration_months = 1

        renewed_count = 0
        total_revenue = 0

        for member_id in member_ids:
            member = Member.query.get(member_id)
            if member:
                renewal_fee = calculate_renewal_fees(
                    renew_period, duration_months)

                if renew_period == 'monthly':
                    new_expiry = datetime.utcnow() + timedelta(days=30 * duration_months)
                else:
                    new_expiry = datetime.utcnow() + timedelta(days=180)

                member.expiry_date = new_expiry
                member.status = 'active'
                member.duration_months = duration_months if renew_period == 'monthly' else 6

                receipt_number = generate_receipt_number()
                payment = Payment(
                    receipt_number=receipt_number,
                    member_id=member.id,
                    amount=renewal_fee,
                    payment_method='Cash',
                    received_by=current_user.username
                )

                payment.set_fee_breakdown({
                    'membership_fee': renewal_fee,
                    'id_card_fee': 0,
                    'wifi_fee': 0,
                    'duration_months': duration_months if renew_period == 'monthly' else 6,
                    'is_renewal': True,
                    'membership_type': renew_period
                })

                db.session.add(payment)
                renewed_count += 1
                total_revenue += renewal_fee

        if renewed_count > 0:
            db.session.commit()
            duration_text = f"{duration_months} month(s)" if renew_period == 'monthly' else "6 months"
            flash(
                f'Successfully renewed {renewed_count} members for {duration_text}. Total revenue: K{total_revenue}', 'success')
        else:
            flash('No members were renewed', 'info')

    except Exception as e:
        db.session.rollback()
        print(f"Error during bulk renewal: {e}")
        flash(f'Error during bulk renewal: {str(e)}', 'error')

    return redirect(url_for('view_members'))


@app.route('/payments')
@login_required
def view_payments():
    try:
        payments = Payment.query.order_by(Payment.payment_date.desc()).all()
        total_revenue = sum(payment.amount for payment in payments)

        return render_template('payments.html',
                               payments=payments,
                               total_revenue=total_revenue,
                               total_payments=len(payments))
    except Exception as e:
        flash(f'Error loading payments: {str(e)}', 'error')
        return render_template('payments.html', payments=[], total_revenue=0, total_payments=0)


@app.route('/member_details/<int:member_id>')
@login_required
def member_details(member_id):
    try:
        member = Member.query.get_or_404(member_id)
        payments = Payment.query.filter_by(member_id=member_id).order_by(
            Payment.payment_date.desc()).all()
        total_paid = sum(payment.amount for payment in payments)

        return render_template('member_details.html',
                               member=member,
                               payments=payments,
                               total_paid=total_paid)
    except Exception as e:
        flash(f'Error loading member details: {str(e)}', 'error')
        return redirect(url_for('view_members'))


@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    member = Member.query.get_or_404(member_id)

    if request.method == 'POST':
        try:
            member.full_name = request.form.get('full_name', '').strip()
            member.email = request.form.get('email', '').strip()
            member.phone = request.form.get('phone', '').strip()
            member.address = request.form.get('address', '').strip()
            member.membership_type = request.form.get('membership_type')

            nrc_number = request.form.get('nrc_number', '').strip()
            if nrc_number:
                member.nrc_number = nrc_number

            nationality = request.form.get('nationality')
            if nationality:
                member.nationality = nationality

            duration_months = request.form.get('duration_months')
            if duration_months:
                try:
                    duration_months = int(duration_months)
                    if duration_months >= 1 and duration_months <= 12:
                        member.duration_months = duration_months
                except (ValueError, TypeError):
                    pass

            photo_file = request.files.get('photo')
            if photo_file and photo_file.filename:
                if allowed_file(photo_file.filename):
                    if member.photo_path:
                        old_photo_path = os.path.join(
                            app.config['UPLOAD_FOLDER'], member.photo_path)
                        if os.path.exists(old_photo_path):
                            os.remove(old_photo_path)

                    filename = secure_filename(photo_file.filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    photo_filename = f"{timestamp}_{filename}"
                    photo_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], photo_filename)
                    photo_file.save(photo_path)

                    try:
                        resize_image(photo_path, output_size=(120, 150))
                    except Exception as resize_error:
                        print(f"⚠️ Could not resize image: {resize_error}")

                    member.photo_path = photo_filename

            db.session.commit()
            flash(
                f'Member {member.full_name} updated successfully!', 'success')
            return redirect(url_for('member_details', member_id=member.id))

        except Exception as e:
            db.session.rollback()
            print(f"Error updating member: {e}")
            flash(f'Error updating member: {str(e)}', 'error')

    return render_template('edit_member.html', member=member)


@app.route('/view_receipt/<int:member_id>')
@login_required
def view_receipt(member_id):
    try:
        member = Member.query.get_or_404(member_id)
        payment = Payment.query.filter_by(member_id=member_id).order_by(
            Payment.payment_date.desc()).first()

        if not payment:
            flash('No payment found for this member', 'error')
            return redirect(url_for('member_details', member_id=member_id))

        return render_template('view_receipt.html',
                               member=member,
                               payment=payment,
                               fee_breakdown=payment.get_fee_breakdown())

    except Exception as e:
        flash(f'Error loading receipt: {str(e)}', 'error')
        return redirect(url_for('member_details', member_id=member_id))


@app.route('/print_receipt/<int:payment_id>')
@login_required
def print_receipt(payment_id):
    try:
        payment = Payment.query.get_or_404(payment_id)
        member = payment.member

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor(ZCAS_COLORS['primary']),
            alignment=1,
            spaceAfter=30
        )

        logo_paths = ['static/images/logo.png', 'images/logo.png']
        logo_exists = False
        logo_path = None

        for path in logo_paths:
            if os.path.exists(path):
                logo_exists = True
                logo_path = path
                break

        if logo_exists:
            try:
                logo = Image(logo_path, width=1.0*inch, height=1.0*inch)
                logo.hAlign = 'LEFT'

                title_table_data = [
                    [logo, Paragraph("ZCAS UNIVERSITY<br/>LIBRARY MANAGEMENT SYSTEM", title_style)]]
                title_table = Table(title_table_data, colWidths=[
                                    1.5*inch, 4.5*inch])
                title_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ]))
                elements.append(title_table)
            except Exception as e:
                print(f"Error adding logo to receipt: {e}")
                elements.append(
                    Paragraph("ZCAS UNIVERSITY - RECEIPT", title_style))
        else:
            elements.append(
                Paragraph("ZCAS UNIVERSITY - RECEIPT", title_style))

        elements.append(Spacer(1, 20))

        receipt_data = [
            ['Receipt Number:', payment.receipt_number],
            ['Date:', payment.payment_date.strftime('%d-%b-%Y %I:%M %p')],
            ['Received From:', member.full_name],
            ['Member ID:', member.member_id],
            ['Payment Method:', payment.payment_method],
            ['Received By:', payment.received_by],
            ['', ''],
            ['Description', 'Amount (K)'],
        ]

        fee_breakdown = payment.get_fee_breakdown()
        if fee_breakdown:
            if fee_breakdown.get('is_renewal'):
                duration_text = f"{fee_breakdown.get('duration_months', 1)} month(s)" if fee_breakdown.get(
                    'membership_type') == 'monthly' else "6 months"
                elements.append(
                    Paragraph(f"<b>Membership Renewal - {duration_text}</b>", styles['Normal']))
                receipt_data.append(
                    ['Membership Fee', f"{fee_breakdown.get('membership_fee', 0):.2f}"])
            else:
                duration_text = f"{fee_breakdown.get('duration_months', 1)} month(s)" if fee_breakdown.get(
                    'membership_type') == 'monthly' else "6 months"
                elements.append(Paragraph(
                    f"<b>Membership Registration - {duration_text}</b>", styles['Normal']))
                receipt_data.append(
                    ['Membership Fee', f"{fee_breakdown.get('membership_fee', 0):.2f}"])
                receipt_data.append(
                    ['ID Card Fee', f"{fee_breakdown.get('id_card_fee', 0):.2f}"])
                receipt_data.append(
                    ['WiFi Fee', f"{fee_breakdown.get('wifi_fee', 0):.2f}"])
        else:
            receipt_data.append(['Total Amount', f"{payment.amount:.2f}"])

        receipt_data.append(['', ''])
        receipt_data.append(
            ['<b>TOTAL AMOUNT:</b>', f"<b>K{payment.amount:.2f}</b>"])

        table = Table(receipt_data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0),
             colors.HexColor(ZCAS_COLORS['primary'])),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (-1, -1), (-1, -1), 'RIGHT'),
            ('FONTNAME', (-1, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (-1, -1), (-1, -1), 14),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 20))

        thank_you = Paragraph(
            "<b>Thank you for your payment!</b>", styles['Normal'])
        elements.append(thank_you)

        footer_style = ParagraphStyle(
            'Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray, alignment=1, spaceBefore=5)

        footer_text = f"""
        {ZCAS_CONTACT['property_notice']}<br/>
        Contact: {ZCAS_CONTACT['phone']} | Email: {ZCAS_CONTACT['email']}<br/>
        Address: {ZCAS_CONTACT['address']} | {ZCAS_CONTACT['website']}
        """
        footer = Paragraph(footer_text, footer_style)
        elements.append(Spacer(1, 10))
        elements.append(footer)

        doc.build(elements)
        buffer.seek(0)

        return send_file(buffer, as_attachment=False,
                         download_name=f"Receipt_{payment.receipt_number}.pdf",
                         mimetype='application/pdf')

    except Exception as e:
        print(f"Error generating receipt: {e}")
        flash(f'Error generating receipt: {str(e)}', 'error')
        return redirect(url_for('view_payments'))


@app.route('/print_id/<int:member_id>')
@login_required
def print_id(member_id):
    member = Member.query.get_or_404(member_id)

    try:
        return render_template('print_id_card.html',
                               member=member,
                               contact_info=ZCAS_CONTACT)

    except Exception as e:
        print(f"Error in print_id: {str(e)}")
        traceback.print_exc()
        flash(f'Error generating ID card: {str(e)}', 'error')
        return redirect(url_for('view_members'))


# ========== RFID SCANNING ROUTES ==========

@app.route('/api/scan_rfid', methods=['POST'])
def api_scan_rfid():
    """API endpoint for RFID reader - finds member by RFID UID or Member ID"""
    try:
        data = request.get_json()
        scanned_id = data.get('rfid_uid', '').strip()

        if not scanned_id:
            return jsonify({
                'success': False,
                'error': 'No RFID UID provided',
                'message': 'Please scan a valid RFID card'
            }), 400

        # First try to find by RFID UID
        member = Member.query.filter_by(rfid_uid=scanned_id).first()

        # If not found by RFID, try by member ID
        if not member:
            member = Member.query.filter_by(member_id=scanned_id).first()

        if not member:
            return jsonify({
                'success': False,
                'error': 'Member not found',
                'message': f'No member found with RFID or ID: {scanned_id}'
            }), 404

        # Check membership expiry
        today = datetime.utcnow().date()
        is_expired = False
        days_remaining = None

        if member.expiry_date:
            expiry_date = member.expiry_date.date() if hasattr(
                member.expiry_date, 'date') else member.expiry_date
            days_remaining = (expiry_date - today).days
            is_expired = days_remaining < 0

            if is_expired and member.status == 'active':
                member.status = 'expired'
                db.session.commit()

        # IMPORTANT: Block expired members from accessing the library
        if is_expired:
            log = AccessLog(
                member_id=member.id,
                action='check_in',
                status='denied',
                message=f'Access DENIED - Membership expired on {member.expiry_date.strftime("%Y-%m-%d")}'
            )
            db.session.add(log)
            db.session.commit()

            photo_url = None
            if member.photo_path:
                photo_url = url_for(
                    'static', filename=f'uploads/{member.photo_path}', _external=True)

            return jsonify({
                'success': False,
                'is_expired': True,
                'member_id': member.member_id,
                'full_name': member.full_name,
                'photo_path': photo_url,
                'message': 'ACCESS DENIED: Your membership has expired. Please renew at the front desk.',
                'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None,
                'days_remaining': days_remaining
            }), 403

        # Check current session status
        current_session = CurrentSession.query.filter_by(
            member_id=member.id).first()

        if current_session:
            # Member is inside - check them out
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

            photo_url = None
            if member.photo_path:
                photo_url = url_for(
                    'static', filename=f'uploads/{member.photo_path}', _external=True)

            return jsonify({
                'success': True,
                'action': 'check_out',
                'member_id': member.member_id,
                'full_name': member.full_name,
                'photo_path': photo_url,
                'message': f'Goodbye {member.full_name}! You have been checked out.',
                'duration_minutes': duration_minutes,
                'check_in_time': current_session.check_in_time.strftime('%I:%M %p'),
                'check_out_time': check_out_time.strftime('%I:%M %p'),
                'rfid_uid': member.rfid_uid
            })
        else:
            # EXTRA SAFETY: Double-check member is not expired before allowing check-in
            if is_expired:
                return jsonify({
                    'success': False,
                    'is_expired': True,
                    'member_id': member.member_id,
                    'full_name': member.full_name,
                    'message': 'ACCESS DENIED: Membership expired. Cannot check in.',
                    'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None
                }), 403

            # Member is outside - check them in
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

            photo_url = None
            if member.photo_path:
                photo_url = url_for(
                    'static', filename=f'uploads/{member.photo_path}', _external=True)

            return jsonify({
                'success': True,
                'action': 'check_in',
                'member_id': member.member_id,
                'full_name': member.full_name,
                'photo_path': photo_url,
                'membership_type': member.membership_type,
                'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None,
                'days_remaining': days_remaining,
                'message': f'Welcome {member.full_name}! Check-in successful.',
                'check_in_time': datetime.utcnow().strftime('%I:%M %p'),
                'rfid_uid': member.rfid_uid
            })

    except Exception as e:
        print(f"Error in scan_rfid: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Server error',
            'message': f'Error processing scan: {str(e)}'
        }), 500


@app.route('/api/check_rfid/<rfid_uid>')
def api_check_rfid(rfid_uid):
    """Check if RFID is already assigned to a member"""
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
    """Assign RFID UID to a member"""
    try:
        data = request.get_json()
        member_id = data.get('member_id')
        rfid_uid = data.get('rfid_uid')

        if not member_id or not rfid_uid:
            return jsonify({'success': False, 'message': 'Missing member ID or RFID UID'}), 400

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
        ).limit(10).all()

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


@app.route('/api/remove_rfid/<int:member_id>', methods=['POST'])
@login_required
def api_remove_rfid(member_id):
    """Remove RFID assignment from a member"""
    try:
        member = Member.query.get_or_404(member_id)
        member.rfid_uid = None
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'RFID removed from {member.full_name}'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== USB READER SCANNING ROUTES (Legacy) ==========

@app.route('/api/scan_member', methods=['POST'])
def api_scan_member():
    """Legacy API endpoint for USB reader - redirects to RFID scan"""
    try:
        data = request.get_json()
        member_id = data.get('member_id')

        with app.test_request_context(json={'rfid_uid': member_id}):
            return api_scan_rfid()

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Server error',
            'message': f'Error processing scan: {str(e)}'
        }), 500


@app.route('/api/current_members')
@login_required
def current_members():
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


@app.route('/access_logs')
@login_required
def access_logs():
    """View access logs page"""
    return render_template('access_logs.html')


@app.route('/api/access_logs')
@login_required
def api_access_logs():
    """
    API endpoint for access logs with advanced filtering.
    Supports filtering by status, user, card ID, date_from, and date_to.
    Returns total logs, check-ins, check-outs summary and paginated results.
    """
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
                'timestamp': access_log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p'),
                'iso_timestamp': access_log.timestamp.isoformat()
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
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/member_photo/<member_id>')
def get_member_photo(member_id):
    """API endpoint to get member photo"""
    try:
        member = Member.query.filter_by(member_id=member_id).first()
        if not member or not member.photo_path:
            return jsonify({'success': False, 'has_photo': False}), 404

        photo_url = url_for(
            'static', filename=f'uploads/{member.photo_path}', _external=True)
        return jsonify({
            'success': True,
            'has_photo': True,
            'photo_url': photo_url,
            'photo_path': member.photo_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/scan_member', methods=['GET'])
@login_required
def scan_member():
    """Page for RFID/USB reader scanning interface"""
    return render_template('scan_member.html')


@app.route('/api/check_membership', methods=['GET', 'POST'])
def api_check_membership():
    """API endpoint for USB reader to check membership status"""
    try:
        if request.method == 'POST':
            data = request.get_json()
            member_id = data.get('member_id') if data else None
        else:
            member_id = request.args.get('member_id')

        if not member_id:
            return jsonify({
                'success': False,
                'error': 'No member ID provided',
                'message': 'Please scan or enter a valid member ID'
            }), 400

        member = Member.query.filter_by(member_id=member_id).first()

        if not member:
            return jsonify({
                'success': False,
                'error': 'Member not found',
                'message': f'No member found with ID: {member_id}',
                'member_id': member_id
            }), 404

        today = datetime.utcnow().date()
        is_expired = False
        days_remaining = None

        if member.expiry_date:
            expiry_date = member.expiry_date.date() if hasattr(
                member.expiry_date, 'date') else member.expiry_date
            days_remaining = (expiry_date - today).days
            is_expired = days_remaining < 0
            if is_expired and member.status == 'active':
                member.status = 'expired'
                db.session.commit()
            elif not is_expired and member.status == 'expired':
                member.status = 'active'
                db.session.commit()

        response = {
            'success': True,
            'member_id': member.member_id,
            'full_name': member.full_name,
            'status': 'EXPIRED' if is_expired else 'ACTIVE',
            'is_expired': is_expired,
            'days_remaining': days_remaining if days_remaining is not None else 0,
            'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None,
            'membership_type': member.membership_type,
            'message': f"Membership {'EXPIRED' if is_expired else 'ACTIVE'} - {member.full_name}"
        }

        if not is_expired and days_remaining is not None:
            if days_remaining <= 7:
                response['warning'] = f'Membership expiring in {days_remaining} days'
                response['message'] += f" (Expires in {days_remaining} days)"
            else:
                response['message'] += f" (Valid until {member.expiry_date.strftime('%d-%b-%Y') if member.expiry_date else 'N/A'})"

        return jsonify(response), 200

    except Exception as e:
        print(f"Error checking membership: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Server error',
            'message': f'Error checking membership: {str(e)}'
        }), 500


@app.route('/api/member/<member_id>')
def get_member_info(member_id):
    """Public API endpoint to get member info by ID (for USB readers)"""
    try:
        member = Member.query.filter_by(member_id=member_id).first()

        if not member:
            return jsonify({'found': False, 'message': 'Member not found'}), 404

        today = datetime.utcnow().date()
        is_expired = False
        if member.expiry_date:
            expiry_date = member.expiry_date.date() if hasattr(
                member.expiry_date, 'date') else member.expiry_date
            is_expired = expiry_date < today

        return jsonify({
            'found': True,
            'member_id': member.member_id,
            'full_name': member.full_name,
            'is_expired': is_expired,
            'status': 'expired' if is_expired else 'active',
            'membership_type': member.membership_type,
            'rfid_assigned': bool(member.rfid_uid)
        })
    except Exception as e:
        return jsonify({'found': False, 'error': str(e)}), 500


@app.route('/reports')
@login_required
def reports():
    try:
        total_members = Member.query.count()
        active_members = Member.query.filter_by(status='active').count()
        expired_members = Member.query.filter_by(status='expired').count()

        payments = Payment.query.all()
        total_revenue = sum(payment.amount for payment in payments)

        monthly_members = Member.query.filter_by(
            membership_type='monthly').count()
        six_months_members = Member.query.filter_by(
            membership_type='six_months').count()

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_registrations = Member.query.filter(
            Member.registration_date >= thirty_days_ago).count()

        return render_template('reports.html',
                               total_members=total_members,
                               active_members=active_members,
                               expired_members=expired_members,
                               total_revenue=total_revenue,
                               monthly_members=monthly_members,
                               six_months_members=six_months_members,
                               recent_registrations=recent_registrations)

    except Exception as e:
        flash(f'Error generating reports: {str(e)}', 'error')
        return render_template('reports.html',
                               total_members=0, active_members=0, expired_members=0,
                               total_revenue=0, monthly_members=0, six_months_members=0, recent_registrations=0)


@app.route('/search')
@login_required
def search_members():
    try:
        query = request.args.get('q', '').strip()

        if not query:
            flash('Please enter a search term', 'error')
            return redirect(url_for('view_members'))

        members = Member.query.filter(
            db.or_(
                Member.full_name.ilike(f'%{query}%'),
                Member.member_id.ilike(f'%{query}%'),
                Member.email.ilike(f'%{query}%'),
                Member.phone.ilike(f'%{query}%'),
                Member.nrc_number.ilike(f'%{query}%')
            )
        ).order_by(Member.registration_date.desc()).all()

        return render_template('search_results.html',
                               members=members,
                               search_query=query,
                               results_count=len(members))

    except Exception as e:
        flash(f'Error searching members: {str(e)}', 'error')
        return redirect(url_for('view_members'))


@app.route('/debug_logo')
def debug_logo():
    logo_paths = [
        os.path.join('static', 'images', 'logo.png'),
        os.path.join('static', 'uploads', 'logo.png'),
        os.path.join('images', 'logo.png'),
        'logo.png'
    ]

    debug_info = {
        'current_working_directory': os.getcwd(),
        'logo_paths_checked': []
    }

    for path in logo_paths:
        exists = os.path.exists(path)
        debug_info['logo_paths_checked'].append({
            'path': path,
            'exists': exists,
            'absolute_path': os.path.abspath(path) if exists else None
        })
        if exists:
            debug_info['found_logo'] = path
            break

    return jsonify(debug_info)


@app.route('/init_admin')
def init_admin():
    try:
        if Admin.query.first():
            flash('Admin user already exists!', 'warning')
            return redirect(url_for('login'))

        admin = Admin(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        flash('Admin user created successfully! Username: admin, Password: admin123', 'success')
        print("✅ Admin user created via init_admin route")
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        flash(f'Error creating admin: {str(e)}', 'error')

    return redirect(url_for('login'))


@app.route('/debug_db')
@login_required
def debug_db():
    try:
        status = {
            'database_uri': app.config['SQLALCHEMY_DATABASE_URI'],
            'current_directory': os.getcwd(),
            'database_file_exists': os.path.exists('library.db'),
            'database_file_size': os.path.getsize('library.db') if os.path.exists('library.db') else 0,
            'table_counts': {
                'admins': Admin.query.count(),
                'members': Member.query.count(),
                'payments': Payment.query.count(),
                'access_logs': AccessLog.query.count(),
                'current_sessions': CurrentSession.query.count()
            },
            'recent_members': [],
            'recent_payments': []
        }

        recent_members = Member.query.order_by(
            Member.registration_date.desc()).limit(5).all()
        for member in recent_members:
            status['recent_members'].append({
                'id': member.id,
                'member_id': member.member_id,
                'name': member.full_name,
                'nrc_number': member.nrc_number if hasattr(member, 'nrc_number') else None,
                'nationality': member.nationality if hasattr(member, 'nationality') else None,
                'registration_date': member.registration_date.strftime('%Y-%m-%d') if member.registration_date else None,
                'expiry_date': member.expiry_date.strftime('%Y-%m-%d') if member.expiry_date else None,
                'rfid_uid': member.rfid_uid if hasattr(member, 'rfid_uid') else None
            })

        recent_payments = Payment.query.order_by(
            Payment.payment_date.desc()).limit(5).all()
        for payment in recent_payments:
            status['recent_payments'].append({
                'id': payment.id,
                'receipt_number': payment.receipt_number,
                'amount': payment.amount,
                'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None
            })

        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Initialize database when app starts
print("🚀 Starting application...")
init_database()

if __name__ == '__main__':
    print("🌐 Starting Flask development server...")
    app.run(debug=True)
