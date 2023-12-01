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
