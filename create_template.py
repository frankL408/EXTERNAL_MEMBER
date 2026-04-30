import os

# Get the current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, 'templates')

# Create templates directory if it doesn't exist
if not os.path.exists(templates_dir):
    os.makedirs(templates_dir)
    print(f"✅ Created templates directory: {templates_dir}")

# Payments.html content
payments_html = '''{% extends "base.html" %}

{% block title %}Payments - ZCAS University Library{% endblock %}

{% block content %}
<div class="container-fluid">
    <div class="row mb-4">
        <div class="col-12">
            <div class="card">
                <div class="card-header bg-primary text-white">
                    <h4 class="mb-0"><i class="fas fa-money-bill-wave"></i> Payment History</h4>
                </div>
                <div class="card-body">
                    <div class="row mb-4">
                        <div class="col-md-4">
                            <div class="card bg-success text-white">
                                <div class="card-body">
                                    <h5 class="card-title">Total Revenue</h5>
                                    <h2 class="mb-0">K{{ "%.2f"|format(total_revenue) }}</h2>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card bg-info text-white">
                                <div class="card-body">
                                    <h5 class="card-title">Total Payments</h5>
                                    <h2 class="mb-0">{{ total_payments }}</h2>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card bg-warning text-dark">
                                <div class="card-body">
                                    <h5 class="card-title">Average Payment</h5>
                                    <h2 class="mb-0">K{{ "%.2f"|format(total_revenue / total_payments if total_payments > 0 else 0) }}</h2>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="table-responsive">
                        <table class="table table-striped table-hover">
                            <thead>
                                <tr>
                                    <th>Receipt #</th>
                                    <th>Member ID</th>
                                    <th>Member Name</th>
                                    <th>Amount (K)</th>
                                    <th>Payment Method</th>
                                    <th>Received By</th>
                                    <th>Date</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for payment in payments %}
                                <tr>
                                    <td>{{ payment.receipt_number }}</td>
                                    <td>{{ payment.member.member_id }}</td>
                                    <td>{{ payment.member.full_name }}</td>
                                    <td><strong>K{{ "%.2f"|format(payment.amount) }}</strong></td>
                                    <td><span class="badge bg-secondary">{{ payment.payment_method }}</span></td>
                                    <td>{{ payment.received_by }}</td>
                                    <td>{{ payment.payment_date.strftime('%Y-%m-%d %H:%M') }}</td>
                                    <td>
                                        <a href="#" class="btn btn-sm btn-info" target="_blank">
                                            <i class="fas fa-print"></i> Receipt
                                        </a>
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="8" class="text-center text-muted py-4">
                                        <i class="fas fa-inbox fa-3x mb-2 d-block"></i>
                                        No payment records found
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}'''

# Write the file
file_path = os.path.join(templates_dir, 'payments.html')
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(payments_html)

print(f"✅ File created: {file_path}")

# Verify the file exists
if os.path.exists(file_path):
    print(f"✅ Verification: File exists at {file_path}")
    print(f"📄 File size: {os.path.getsize(file_path)} bytes")
else:
    print(f"❌ File was not created!")
