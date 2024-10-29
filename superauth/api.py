import frappe
from frappe.auth import LoginManager
import random
from datetime import datetime, timedelta
from frappe.utils.password import update_password

# ----------------------- LOGIN FUNCTION -----------------------
@frappe.whitelist(allow_guest=True)
def app_login(usr, pwd):
    login_manager = LoginManager()
    login_manager.authenticate(usr, pwd)
    login_manager.post_login()

    if frappe.response['message'] == 'Logged In':
        user = login_manager.user
        frappe.response['key_details'] = generate_key(user)
        frappe.response['user_details'] = get_user_details(user)
        
        company_name = frappe.db.get_value("Employee", {"user_id": user}, "company")
        
        if company_name:
            company_details = get_company_details(company_name)
            frappe.response['company_details'] = company_details

            address_links = frappe.get_all(
                "Dynamic Link",
                filters={"link_doctype": "Company", "link_name": company_name, "parenttype": "Address"},
                fields=["parent"]
            )

            if address_links:
                address_names = [link['parent'] for link in address_links]
                address_details = frappe.get_all(
                    "Address",
                    filters={"name": ["in", address_names]},
                    fields=["address_title", "address_type", "address_line1", "city", "country", "phone", "is_your_company_address"]
                )
                frappe.response['company_details']['addresses'] = address_details
            else:
                frappe.response['company_details']['addresses'] = []
        else:
            frappe.throw("No company found for the user.")
    else:
        return False
# ----------------------- HELPER FUNCTIONS -----------------------
def generate_key(user):
    user_details = frappe.get_doc("User", user)
    api_secret = api_key = ''
    if not user_details.api_key and not user_details.api_secret:
        api_secret = frappe.generate_hash(length=15)
        api_key = frappe.generate_hash(length=15)
        user_details.api_key = api_key
        user_details.api_secret = api_secret
        user_details.save(ignore_permissions=True)
    else:
        api_secret = user_details.get_password('api_secret')
        api_key = user_details.get('api_key')
    return {"api_secret": api_secret, "api_key": api_key}

def get_user_details(user):
    user_details = frappe.get_all("User", filters={"name": user}, fields=["name", "first_name", "last_name", "email", "mobile_no", "gender", "role_profile_name"])
    if user_details:
        return user_details[0]
    return {}

def get_company_details(company_name):
    company_details = frappe.get_all("Company", filters={"name": company_name}, fields=["*"])
    if company_details:
        return company_details[0]
    else:
        frappe.throw(f"No company found with name {company_name}")
# ----------------------- SIGNUP FUNCTION -----------------------
@frappe.whitelist(allow_guest=True)
def signup(**kwargs):
    try:
        required_fields = ["company_name", "address", "email", "first_name", "last_name", "new_password", "gender", "dob", "doj", "mobile_no", "city"]
        for field in required_fields:
            if field not in kwargs:
                raise KeyError(field)

        user_email = kwargs["email"]

        new_company = create_company_with_address(
            company_name=kwargs["company_name"],
            address_line1=kwargs["address"],
            city=kwargs["city"],
            phone=kwargs["mobile_no"],
            email_id=user_email  
        )

        if new_company:
            new_user = create_user(
                email=user_email,
                first_name=kwargs["first_name"],
                last_name=kwargs["last_name"],
                phone_number=kwargs.get("phone_number"),
                mobile_no=kwargs["mobile_no"],
                new_password=kwargs["new_password"]
            )
            employee_id = add_user_as_employee(
                user_email=new_user.name,
                employee_name=f"{new_user.first_name} {new_user.last_name}",
                company_name=new_company["company"].name,
                gender=kwargs["gender"],
                date_of_birth=kwargs["dob"],
                date_of_joining=kwargs["doj"]
            )

            welcome_email_html = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to OmniInvoice!</title>
            </head>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eaeaea; border-radius: 8px;">
                    <h2 style="color: #2c3e50;">Welcome to OmniInvoice!</h2>
                    <p>We're excited to have you on board. Get started by accessing your mail on our platform:</p>
                    <a href="https://randombooks.vercel.app/" style="display: inline-block; padding: 10px 20px; margin: 10px 0; font-size: 16px; color: #fff; background-color: #FE5632; text-decoration: none; border-radius: 5px;">Go to Invoice App</a>
                    <p>Looking for more? Be sure to <a href="https://randomsuite.vercel.app/products" style="color: #3498db;">check out our Products page</a> for a complete suite of tools to streamline your workflow.</p>
                    <p>Best wishes,<br>OmniInvoice Team</p>
                </div>
            </body>
            </html>
            """

            frappe.sendmail(
                recipients=[user_email],
                subject="Welcome to OmniInvoice!",
                message=welcome_email_html,
                delayed=False
            )

            return {
                "message": "Signup successful",
                "user": new_user,
                "company": new_company["company"],
                "address": new_company["address"],
                "employee_id": employee_id
            }
        else:
            return {"message": "Signup was not successful: Company creation failed."}
    except KeyError as e:
        return {"message": f"Missing required field: {e.args[0]}"}
    except frappe.ValidationError as e:
        return {"message": f"Validation error: {e}"}
    except Exception as e:
        return {"message": f"An unexpected error occurred: {e}"}

# ----------------------- COMPANY AND ADDRESS CREATION -----------------------
def create_company_with_address(company_name, address_line1, city, phone, email_id, address_type="Billing"):
    doctype = "Company"
    chart_of_accounts = "Standard with Numbers"
    default_currency = "BDT"
    country = "Bangladesh"
    
    try:
        if frappe.db.exists("Company", company_name):
            frappe.throw("Company already exists.")
        
        company = frappe.get_doc({
            "doctype": doctype,
            "company_name": company_name,
            "default_currency": default_currency,
            "country": country,
            "chart_of_accounts": chart_of_accounts
        })
        company.insert(ignore_permissions=True)

        address = frappe.get_doc({
            "doctype": "Address",
            "address_title": company_name,
            "address_type": address_type,
            "address_line1": address_line1,
            "city": city,
            "phone": phone,
            "country": country,
            "email_id": email_id,  
            "is_your_company_address": 1,
            "links": [{
                "link_doctype": "Company",
                "link_name": company.name
            }]
        })
        address.insert(ignore_permissions=True)

        frappe.db.commit()

        return {"company": company, "address": address}

    except frappe.ValidationError as e:
        frappe.throw(f"Validation error: {e}")
    except Exception as e:
        frappe.throw(f"An unexpected error occurred: {e}")

# ----------------------- USER CREATION -----------------------
def create_user(email, first_name, last_name, phone_number, mobile_no, new_password):
    user_doctype = "User"
    omni_invoice_role_profile = "OmniInvoice User"
    user_type = "System User"
    try:
        if frappe.db.exists("User", email):
            frappe.throw("User already exists.")
        user = frappe.get_doc({
            "doctype": user_doctype,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": phone_number,
            "mobile_no": mobile_no,
            "enabled": 1,
            "user_type": user_type,
            "send_welcome_email":0,
            "role_profile_name": omni_invoice_role_profile
        })
        user.insert(ignore_permissions=True)
        frappe.utils.password.update_password(user.name, new_password)
        frappe.db.commit()
        return user
    except frappe.ValidationError as e:
        frappe.throw(f"Validation error: {e}")
    except Exception as e:
        frappe.throw(f"An unexpected error occurred: {e}")

# ----------------------- EMPLOYEE CREATION -----------------------
def add_user_as_employee(user_email, employee_name, company_name, gender, date_of_birth, date_of_joining):
    user = frappe.get_doc("User", user_email)
    if not user:
        raise Exception("User does not exist")
    employee = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": employee_name,
        "user_id": user_email,
        "company": company_name,
        "status": "Active",
        "first_name": user.first_name,
        "gender": gender,
        "date_of_birth": date_of_birth,
        "date_of_joining": date_of_joining
    })
    employee.insert(ignore_permissions=True)
    frappe.db.commit()
    return employee.name
# ----------------------- FORGOT PASSWORD -----------------------
@frappe.whitelist(allow_guest=True)
def forgot_password(email):
    if not frappe.db.exists("User", email):
        frappe.throw("Email is not registered")

    verification_code = str(random.randint(100000, 999999))

    reset_doc = frappe.get_doc({
        "doctype": "Password Reset",
        "user_email": email,
        "verification_code": verification_code,
        "expiration": datetime.now() + timedelta(minutes=10),  # Code expires in 10 minutes
        "is_verified": 0,
        "is_used": 0
    })
    reset_doc.insert(ignore_permissions=True)

    frappe.sendmail(
        recipients=email,
        subject="Password Reset Verification Code",
        message=f"Your verification code is {verification_code}. Use this to reset your password."
    )

    masked_email = f"{email.split('@')[0]}@{'*' * (len(email.split('@')[1]) - 2)}{email.split('@')[1][-2:]}"
    return f"Verification code sent to '{masked_email}'"

# ----------------------- VERIFY CODE -----------------------
@frappe.whitelist(allow_guest=True)
def verify_code(email, code):
    reset_record = frappe.get_all(
        "Password Reset",
        filters={"user_email": email, "verification_code": code, "is_verified": 0, "is_used": 0},
        fields=["name", "expiration"]
    )

    if not reset_record:
        frappe.throw("Invalid or expired verification code.")

    expiration = reset_record[0]["expiration"]
    if expiration and datetime.now() > expiration:
        frappe.throw("The verification code has expired. Request a new one.")

    reset_doc = frappe.get_doc("Password Reset", reset_record[0]["name"])
    reset_doc.is_verified = 1
    reset_doc.save(ignore_permissions=True)

    return "Code verified. Proceed to reset your password."

# ----------------------- RESET PASSWORD -----------------------
@frappe.whitelist(allow_guest=True)
def reset_password(email, new_password, confirm_password):
    if new_password != confirm_password:
        frappe.throw("Passwords do not match")

    verified_record = frappe.get_all(
        "Password Reset",
        filters={"user_email": email, "is_verified": 1, "is_used": 0},
        fields=["name"]
    )

    if not verified_record:
        frappe.throw("Password reset not allowed without verified OTP. Please verify the OTP first.")

    update_password(email, new_password)

    reset_doc = frappe.get_doc("Password Reset", verified_record[0]["name"])
    reset_doc.is_used = 1
    reset_doc.save(ignore_permissions=True)

    frappe.db.delete("Password Reset", {"user_email": email, "is_used": 1})

    frappe.sendmail(
        recipients=email,
        subject="Your Password Has Been Changed",
        message="""
        <p>Dear User,</p>
        <p>Your password has been successfully changed. If you did not request this change, please contact our support team immediately.</p>
        <p>Best regards,<br>OmniInvoice Team</p>
        """,
        delayed=False
    )

    return "Password reset successful. You can now log in with the new password."
