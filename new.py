# Author Auguspay Team
# Work Under Progress

#Segno library to genrate the QR code
import segno
from gtts import gTTS
import os

#used for calling to other files
import subprocess

#library to generate the pdf of QR code
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Function used to generate the QR code for merchant unique amount
def generate_upi_fixqr_code(vpa, amount, name, description):
    upi_url = f"upi://pay?pa={vpa}&pn=AuguspayUser&am={amount}&tn={description}"
    qr = segno.make(upi_url)
    return qr

#Fucntion used to generate the normal QR 
def generate_upi_norqr_code(vpa,name):
    upi_url=f"upi://pay?pa={vpa}&pn=AuguspayUser"
    qr=segno.make(upi_url)
    return qr

#function to generate the pdf and specific position
def add_image_to_pdf(pdf, image_path, x, y, width, height):
    pdf.drawImage(image_path, x, y, width, height)

def generate_pdf(pdf_path):    
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

#main fucntion
if __name__ == "__main__":
    a = input(
            "what you want\n1.Qr code for yourself \n2.For the pay on delievery payment\n")
    if (a == "2"):
        print("You have input file? y:n")
        a=input()
        #this code is for taking input file as file I/O
        if(a=='y'):
            p=[]
            t=0
            r=input("Enter the name of input file you have?")
            with open(r) as fp:
                line = fp.readline()
                cnt = 1
                while line:
                    s=line.strip()
                    p.append(s)
                    line = fp.readline()
                    cnt += 1
                    t+=1
            print(p)
            t=0
            vpa = p[t]
            t+=1
            name = p[t]
            mytext = f"Hi {name}, Your Qr code is ready!"
            t+=1
            n=int(p[t])
            t+=1
            for i in range(0,n):
                amount = p[t]
                t+=1
                description = p[t]
                t+=1
                qr_code_image = generate_upi_fixqr_code(vpa, amount, name, description)
                qr_code_image.save(f"code_upi.png", dark="black",
                                light="white", border=5, scale=5)
                pdf_path = f"uploads/output{i}.pdf"
                generate_pdf(pdf_path)
            subprocess.run(["python", "zip.py"])
            subprocess.run(["python", "Mail_zip.py"])

        else:
            vpa = input("Enter receiver Vpa means (upi id):- ")
            name = input("Receiver Name:- ")
            mytext = f"Hi {name}, Your Qr code is ready!"
            n=int(input())
            for i in range(0,n):
                amount = input("Enter Fix amount you want from user:- ")
                description = input("Description for the payment:- ")
                qr_code_image = generate_upi_fixqr_code(vpa, amount, name, description)
                if(qr_code_image==False):
                    print("Cross Site attack")
                qr_code_image.save(f"code_upi.png", dark="black",
                                light="white", border=5, scale=5)
                pdf_path = f"uploads/output{i}.pdf"
                generate_pdf(pdf_path)
            subprocess.run(["python", "zip.py"])
            subprocess.run(["python", "Mail_zip.py"])

    else:
        vpa = input("Enter receiver Vpa means (upi id):- ")
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
            name = input("Receiver company Name:- ")
            mytext = f"Hi {name}, Your Qr code is ready!"
            qr_code=generate_upi_norqr_code(vpa,name)
            qr_code.save("code_upi.png", dark="black",
                light="white", border=5, scale=5)
            pdf_path = f"output0.pdf"
            generate_pdf(pdf_path)
            subprocess.run(["python", "mail.py"])

#mail system
#End-- code