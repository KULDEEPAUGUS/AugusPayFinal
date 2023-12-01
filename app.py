from flask import Flask, render_template, request, send_file
import qrcode
from reportlab.pdfgen import canvas

app = Flask(__name__)

#Segno library to genrate the QR code
import segno
from gtts import gTTS
import os

#library for email Simple Mail Transfer Protocol
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

#library to call
from cryptography.fernet import Fernet
from PyPDF2 import PdfWriter, PdfReader

#used for calling to other files
import subprocess

#library to generate the pdf of QR code
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

@app.route('/')
def index():
    return render_template('index.html')


#Fucntion used to generate the normal QR 
def generate_upi_norqr_code(vpa,name):
    upi_url=f"upi://pay?pa={vpa}&pn=AuguspayUser"
    qr=segno.make(upi_url)
    return qr

#function to generate the pdf and specific position
def add_image_to_pdf(pdf, image_path, x, y, width, height):
    pdf.drawImage(image_path, x, y, width, height)

def generate_(pdf_path):    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    # Define image paths and positions
    images = [
        {"path": "./augusscanner.png", "x": 200, "y": 300, "width": 250, "height": 350},
        {"path": "./code_upi.png", "x": 235, "y": 370, "width": 180, "height": 185},   
    ]

    # Add images to the PDF
    for image_info in images:

        add_image_to_pdf(c, image_info["path"], image_info["x"], image_info["y"], image_info["width"], image_info["height"])
    c.save()

def generate_upi_fixqr_code(vpa, amount, name, description):
    upi_url = f"upi://pay?pa={vpa}&pn=AuguspayUser&am={amount}&tn={description}"
    qr = segno.make(upi_url)
    return qr


@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
     vpa = request.form['vpa']
     chk=False;
     for char in vpa:
        if(char=='>' or char=='<'):
            print("Cross Script Attack")
            break
        if(char=='@'):
            chk=True;
     if(chk==False):
        print("Cross Script Attack")
     elif(chk==True):
        name = request.form['Name']
        mytext = f"Hi {name}, Your Qr code is ready!"
        qr_code=generate_upi_norqr_code(vpa,name)
        qr_code.save("code_upi.png", dark="black",
            light="white", border=5, scale=5)
        pdf_path = f"output0.pdf"
        generate_(pdf_path)

        name=request.form['Name']
        Email=request.form['email']
        # pdf creation 
        out = PdfWriter() 
        file = PdfReader("./output0.pdf") 
        num = len(file.pages) 
        for idx in range(num): 
            page = file.pages[idx]
            out.add_page(page) 
        mess=name
        #pdf protection using cipher text
        key = Fernet.generate_key()
        cipher_suite = Fernet(key)
        message = mess.encode('ASCII')
        cipher_text = cipher_suite.encrypt(message)
        plain_text = cipher_suite.decrypt(cipher_text)

        passw=cipher_text[0:16]
        
        #psswd for the pdf in cipher
        passw = f"{passw}"

        out.encrypt(passw) 
        with open("myfile_encrypted.pdf", "wb") as f: 
            out.write(f)
        # return send_file('./myfile_encrypted.pdf',as_attachment=True)
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
Password: [{passw}]
Keep it confidential. For assistance, contact us.

Thank you for choosing Auguspay.
Warm regards,

[Auguspay team]
[Email:- auguspayteam@gmail.com]"""

        msg.attach(MIMEText(body, 'plain'))

        # Add the file path to attach
        file_path = './myfile_encrypted.pdf'  # Replace with file path

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
            server.sendmail(sender_email, receiver_email, msg.as_string())
        return render_template('index.html', predict_content="Email Sent Successfully")

@app.route('/ecommerce', methods=['POST'])
def ecommerce():
    p=[]
    t=0
    r=request.files['file']
    r.save(os.path.join('./static/uploads', r.filename))
    with open(r) as fp:
        line = fp.readline()
        cnt = 1
        while line:
            s=line.strip()
            p.append(s)
            line = fp.readline()
            cnt += 1
            t+=1
    vpa =request.form['vpa']
    name = request.form['Name']
    n=int(p[t])
    t=0
    for i in range(0,n):
        amount = p[t]
        t+=1
        description = p[t]
        t+=1
        qr_code_image = generate_upi_fixqr_code(vpa, amount, name, description)
        qr_code_image.save(f"code_upi.png", dark="black",
                        light="white", border=5, scale=5)
        pdf_path = f"./static/uploads/output{i}.pdf"
        generate_(pdf_path)
    import os
    from zipfile import ZipFile
    def zip_folder(folder_path, output_zip):
        with ZipFile(output_zip, 'w') as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname=arcname)
    # Example Usage
    folder_path = './static/uploads'  # Replace with the path to your folder
    output_zip = 'output.zip'  # Replace with desired output zip file path
    zip_folder(folder_path, output_zip)

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    #library to call
    from cryptography.fernet import Fernet
    from PyPDF2 import PdfWriter, PdfReader 

    name=request.form['Name']

    Email=request.form['email']

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
    return render_template('index.html', predict_content="Email Sent Successfully")

@app.route('/fixamnt', methods=['POST'])
def fixamnt():
    vpa = request.form['vpa']
    name = request.form['name']
    amount = request.form['amount']
    description = request.form['descp']
    qr_code_image = generate_upi_fixqr_code(vpa, amount, name, description)
    if(qr_code_image==False):
        print("Cross Site attack")
    qr_code_image.save(f"code_upi.png", dark="black",
                    light="white", border=5, scale=5)
    pdf_path = f"./static/uploads/output.pdf"
    generate_(pdf_path)

    name=request.form['name']
    Email=request.form['email']
    # pdf creation 
    out = PdfWriter() 
    file = PdfReader("./static/uploads/output.pdf") 
    num = len(file.pages) 
    for idx in range(num): 
        page = file.pages[idx]
        out.add_page(page) 
    mess=name
    #pdf protection using cipher text
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    message = mess.encode('ASCII')
    cipher_text = cipher_suite.encrypt(message)
    plain_text = cipher_suite.decrypt(cipher_text)

    passw=cipher_text[0:16]
    
    #psswd for the pdf in cipher
    passw = f"{passw}"

    out.encrypt(passw) 
    with open("./static/uploads/myfile_encrypted.pdf", "wb") as f: 
        out.write(f)
    # return send_file('./myfile_encrypted.pdf',as_attachment=True)
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
Password: [{passw}]
Keep it confidential. For assistance, contact us.

Thank you for choosing Auguspay.
Warm regards,

[Auguspay team]
[Email:- auguspayteam@gmail.com]"""

    msg.attach(MIMEText(body, 'plain'))

    # Add the file path to attach
    file_path = './static/uploads/myfile_encrypted.pdf'  # Replace with file path

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
        server.sendmail(sender_email, receiver_email, msg.as_string())
    return render_template('index.html', predict_content="Email Sent Successfully")

@app.route('/contact', methods=['POST'])
def contact():
    name=request.form['name']
    Email=request.form['email']
    # Set up the SMTP server
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587  # Use 465 for SSL or 587 for TLS

    # Login credentials
    sender_email = 'auguspayteam@gmail.com'
    password = 'zeyy chyx xvvv qwzd'

    receiver_email = 'auguspayteam@gmail.com'
    Subject=request.form['subject']
    message=request.form['message']
    # Create a message object
    msg = MIMEMultipart()
    msg['From'] = 'auguspayteam@gmail.com'
    msg['To'] = Email
    msg['Subject'] = Subject

    # Attach the message body
    body = f"""Hello Auguspayteam,
{message}
{name}
{Email}
"""
    msg.attach(MIMEText(body, 'plain'))
    # Initialize the SMTP server
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()  # Enable TLS encryption
        server.login(sender_email, password)  # Login to your email account
        server.sendmail(sender_email, receiver_email, msg.as_string())
    return render_template('index.html', predict_content="Email Sent Successfully")

if __name__ == '__main__':
    app.run(debug=True)
