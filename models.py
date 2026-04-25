from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json

db = SQLAlchemy()


class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    address = db.Column(db.Text, nullable=False)
    # 'monthly' or 'six_months'
    membership_type = db.Column(db.String(20), nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=False)
    photo_path = db.Column(db.String(200))
    status = db.Column(db.String(20), default='active')
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    receipt_number = db.Column(db.String(20), unique=True)

    def calculate_fees(self):
        if self.membership_type == 'monthly':
            return 90
        else:  # six_months
            return 500

    def calculate_expiry(self):
        if self.membership_type == 'monthly':
            return datetime.utcnow() + timedelta(days=30)
        else:  # six_months
            return datetime.utcnow() + timedelta(days=180)

    def is_expired(self):
        return datetime.utcnow() > self.expiry_date

    def get_fees_breakdown(self):
        if self.membership_type == 'monthly':
            return [
                {"description": "Monthly Subscription", "amount": 90},
                {"description": "ID Card Fee", "amount": 100},
                {"description": "WiFi Access Fee", "amount": 120},
                {"description": "Subtotal", "amount": 310},
                {"description": "Discount", "amount": -220},
                {"description": "TOTAL PAYABLE", "amount": 90}
            ]
        else:
            return [
                {"description": "Six Months Subscription", "amount": 500},
                {"description": "ID Card Fee", "amount": 100},
                {"description": "WiFi Access Fee", "amount": 120},
                {"description": "Subtotal", "amount": 720},
                {"description": "Discount", "amount": -220},
                {"description": "TOTAL PAYABLE", "amount": 500}
            ]


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(20), unique=True, nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey(
        'member.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50), default='Cash')
    received_by = db.Column(db.String(100), nullable=False)
    fee_breakdown = db.Column(db.Text)  # Store as JSON string

    member = db.relationship(
        'Member', backref=db.backref('payments', lazy=True))

    def set_fee_breakdown(self, breakdown_dict):
        """Store fee breakdown as JSON string"""
        if breakdown_dict:
            self.fee_breakdown = json.dumps(breakdown_dict)
        else:
            self.fee_breakdown = None

    def get_fee_breakdown(self):
        """Retrieve fee breakdown as dictionary"""
        if self.fee_breakdown:
            try:
                return json.loads(self.fee_breakdown)
            except json.JSONDecodeError:
                return {}
        return {}
