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

# Bank Details
BANK_DETAILS = {
    'bank_name': 'Zanaco Bank Zambia',
    'account_name': 'ZCAS University - Library Fees Collection',
    'account_number': '5823001300137',
    'branch': 'Lusaka Main Branch',
    'sort_code': '01-01-01',
    'swift_code': 'ZANAZMLU'
}

# Fee Structure
FEE_STRUCTURE = {
    'id_card': 100,
    'wifi': 120,
    'monthly': 90,
    'six_months': 500,
    'student': 50,
    'staff': 75,
    'external': 100
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
    return f"ZCAS-QTN-{timestamp}-{random_num}"


def calculate_total_fees(membership_type, duration_months=1):
    """Calculate total fees based on membership type and duration"""
    if membership_type == 'monthly':
        membership_fee = FEE_STRUCTURE['monthly'] * duration_months
    elif membership_type == 'six_months':
        membership_fee = FEE_STRUCTURE['six_months']
        duration_months = 6
    elif membership_type == 'student':
        membership_fee = FEE_STRUCTURE['student'] * duration_months
    elif membership_type == 'staff':
        membership_fee = FEE_STRUCTURE['staff'] * duration_months
    else:
        membership_fee = FEE_STRUCTURE['external'] * duration_months

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


@app.context_processor
def inject_template_vars():
    return {
        'bank_details': BANK_DETAILS,
        'now': datetime.utcnow(),
        'colors': ZCAS_COLORS,
        'fee_structure': FEE_STRUCTURE,
        'contact_info': ZCAS_CONTACT
    }


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

        # Get recent members for dashboard display
        members = Member.query.order_by(
            Member.registration_date.desc()).limit(10).all()

        # Calculate revenue stats
        payments = Payment.query.all()
        monthly_revenue = 0
        six_months_revenue = 0
        total_revenue = 0

        for payment in payments:
            fee_breakdown = payment.get_fee_breakdown()
            if fee_breakdown.get('membership_type') == 'monthly':
                monthly_revenue += payment.amount
            elif fee_breakdown.get('membership_type') == 'six_months':
                six_months_revenue += payment.amount
            total_revenue += payment.amount

        # Get membership type counts
        monthly_members = Member.query.filter_by(
            membership_type='monthly').count()
        six_months_members = Member.query.filter_by(
            membership_type='six_months').count()

        return render_template('dashboard.html',
                               total_members=total_members,
                               active_members=active_members,
                               expired_members=expired_members,
                               current_in_library=current_in_library,
                               members=members,
                               monthly_members=monthly_members,
                               six_months_members=six_months_members,
                               monthly_revenue=monthly_revenue,
                               six_months_revenue=six_months_revenue,
                               total_revenue=total_revenue)
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        traceback.print_exc()
        return render_template('dashboard.html',
                               total_members=0,
                               active_members=0,
                               expired_members=0,
                               current_in_library=0,
                               members=[],
                               monthly_members=0,
                               six_months_members=0,
                               monthly_revenue=0,
                               six_months_revenue=0,
                               total_revenue=0)


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


# ========== ACCESS LOGS PAGE ROUTE ==========

@app.route('/access_logs')
@login_required
def access_logs():
    """View access logs page"""
    return render_template('access_logs.html')


# ========== CALENDAR ROUTES ==========

@app.route('/calendar')
@login_required
def calendar_view():
    """Calendar view for membership expiries and registrations"""
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

        return render_template('calendar.html',
                               calendar_events=calendar_events,
                               upcoming_events=upcoming_events)

    except Exception as e:
        print(f"Error loading calendar events: {e}")
        flash(f'Error loading calendar: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# ========== MEMBER MANAGEMENT ROUTES ==========

@app.route('/member_details/<int:member_id>')
@login_required
def member_details(member_id):
    """View member details"""
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


@app.route('/renew_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
def renew_member(member_id):
    """Renew member membership"""
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

            # Calculate renewal fee
            if renew_period == 'monthly':
                renewal_fee = FEE_STRUCTURE['monthly'] * duration_months
                new_expiry = renewal_date + \
                    timedelta(days=30 * duration_months)
            elif renew_period == 'six_months':
                renewal_fee = FEE_STRUCTURE['six_months']
                new_expiry = renewal_date + timedelta(days=180)
            else:
                renewal_fee = FEE_STRUCTURE['external'] * duration_months
                new_expiry = renewal_date + \
                    timedelta(days=30 * duration_months)

            member.expiry_date = new_expiry
            member.status = 'active'
            member.membership_type = renew_period

            # Create payment record
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
                'is_renewal': True,
                'membership_type': renew_period,
                'duration_months': duration_months if renew_period == 'monthly' else 6
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


@app.route('/members')
@login_required
def view_members():
    try:
        members = Member.query.order_by(Member.registration_date.desc()).all()
        return render_template('members.html', members=members)
    except Exception as e:
        flash(f'Error loading members: {str(e)}', 'error')
        return render_template('members.html', members=[])


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
            duration_months = request.form.get('duration_months', '1')
            payment_method = request.form.get('payment_method', 'Cash')
            nationality = request.form.get('nationality', 'Zambian')

            # Validate required fields
            if not all([full_name, email, phone, address, nrc_number, membership_type]):
                flash('Please fill in all required fields', 'error')
                return render_template('register_member.html')

            # Convert duration_months to int
            try:
                duration_months = int(duration_months)
                if duration_months < 1:
                    duration_months = 1
                elif duration_months > 12:
                    duration_months = 12
            except (ValueError, TypeError):
                duration_months = 1

            # Calculate fees
            fees = calculate_total_fees(membership_type, duration_months)

            member_id = generate_member_id()
            registration_date = datetime.utcnow()
            receipt_number = generate_receipt_number()

            # Handle photo upload
            photo_file = request.files.get('photo')
            photo_filename = None
            if photo_file and photo_file.filename:
                if allowed_file(photo_file.filename):
                    filename = secure_filename(photo_file.filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    photo_filename = f"{timestamp}_{filename}"
                    photo_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], photo_filename)
                    photo_file.save(photo_path)

            # Create member
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
                status='active',
                rfid_uid=None
            )

            # Set expiry date
            if membership_type == 'monthly':
                member.expiry_date = registration_date + \
                    timedelta(days=30 * fees['duration_months'])
            elif membership_type == 'six_months':
                member.expiry_date = registration_date + timedelta(days=180)
            else:
                member.expiry_date = registration_date + \
                    timedelta(days=30 * fees['duration_months'])

            db.session.add(member)
            db.session.flush()

            # Create payment record
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

            duration_text = f"{fees['duration_months']} month(s)" if membership_type in [
                'monthly', 'student', 'staff', 'external'] else "6 months"
            flash(
                f'Member registered successfully! Member ID: {member.member_id}. Duration: {duration_text}. Total Fees: K{fees["total"]}',
                'success'
            )
            return redirect(url_for('view_members'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ Registration error: {e}")
            traceback.print_exc()
            flash(f'Error registering member: {str(e)}', 'error')
            return render_template('register_member.html')


@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    """Edit member information"""
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

            # Handle photo upload
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


@app.route('/print_id/<int:member_id>')
@login_required
def print_id(member_id):
    """Print ID card for member"""
    member = Member.query.get_or_404(member_id)

    try:
        return render_template('print_id_card.html',
                               member=member,
                               contact_info=ZCAS_CONTACT)
    except Exception as e:
        print(f"Error in print_id: {str(e)}")
        traceback.print_exc()
        flash(f'Error generating ID card: {str(e)}', 'error')
        return redirect(url_for('member_details', member_id=member.id))


@app.route('/print_quotation/<int:payment_id>')
@login_required
def print_quotation(payment_id):
    """Print quotation for payment"""
    try:
        payment = Payment.query.get_or_404(payment_id)
        member = payment.member

        return render_template('print_quotation.html',
                               payment=payment,
                               member=member,
                               contact_info=ZCAS_CONTACT,
                               bank_details=BANK_DETAILS)
    except Exception as e:
        print(f"Error in print_quotation: {e}")
        traceback.print_exc()
        flash(f'Error generating quotation: {str(e)}', 'error')
        return redirect(url_for('view_payments'))


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


# ========== PAYMENTS AND REPORTS ROUTES ==========

@app.route('/payments')
@login_required
def view_payments():
    """View all payments"""
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


@app.route('/reports')
@login_required
def reports():
    """Generate reports"""
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


# Initialize database when app starts
print("🚀 Starting application...")
init_database()

if __name__ == '__main__':
    print("🌐 Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
