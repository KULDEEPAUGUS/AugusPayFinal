import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

#library to call
from cryptography.fernet import Fernet
from PyPDF2 import PdfWriter, PdfReader 


name=input("Enter your Name:- ")

Email=input("Enter your email id :- ")

# Set up the SMTP server
smtp_server = 'smtp.gmail.com'
smtp_port = 587  # Use 465 for SSL or 587 for TLS

# Login credentials
sender_email = 'auguspayteam@gmail.com'
password = 'zeyy chyx xvvv qwzd'

# Recipient's email address

receiver_email = Email

# Create a message object
msg = MIMEMultipart()
msg['From'] = 'auguspayteam@gmail.com'
msg['To'] = Email
msg['Subject'] = 'Important: Your Secure Payment QR Code from Auguspay'

# Attach the message body
body = f"""Dear {name},
Greetings from Auguspay!

Attached is your payment QR code in a password-protected PDF. 
Password: []
Keep it confidential. For assistance, contact us.

Thank you for choosing Auguspay.
Warm regards,

[Auguspay team]
[Email:- auguspayteam@gmail.com]"""

msg.attach(MIMEText(body, 'plain'))

# Add the file path to attach
file_path = 'uploads.zip'  # Replace with file path

# Open the file in binary mode
with open(file_path, 'rb') as attachment:
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(attachment.read())

# Encode the attachment
encoders.encode_base64(part)
part.add_header('Content-Disposition', "attachment; filename= %s" % file_path)

# Attach the attachment to the message
msg.attach(part)

# Initialize the SMTP server
with smtplib.SMTP(smtp_server, smtp_port) as server:
    server.starttls()  # Enable TLS encryption
    server.login(sender_email, password)  # Login to your email account
    
    # Send the email
    server.sendmail(sender_email, receiver_email, msg.as_string())

print('Email sent successfully!')
