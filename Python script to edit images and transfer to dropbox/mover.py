from csv import reader
from PIL import Image, ImageFont, ImageDraw
from pathlib import Path
import os
import piexif
import time
from fractions import Fraction
import logging
import shutil

# Changable variables, so its easier to change throughout the code if for example a column name changes
config_path = 'mover_config.csv'
windows_server_folder = 'windows_server_folder'
destination_folder = 'destination_folder'
size = 'size'
text = 'text'
font = 'font' 
font_size = 'font_size'
name_prefix = 'name_prefix'
latitude = 'latitude'
longitude = 'longitude'
extension = '.jpg'
dimension_splitter = 'x'
watermark_fill = (255, 255, 255, 128)
error_pile = 'E:\\photos\\failed'

logging.basicConfig(filename="log.txt", level=logging.DEBUG, filemode="w")
logging.getLogger("PIL.TiffImagePlugin").disabled = True
logging.getLogger("urllib3.connectionpool").disabled = True
logging.getLogger("dropbox").disabled = True

fonts = {

}

def to_deg(value, loc):
    if value < 0:
        loc_value = loc[0]
    elif value > 0:
        loc_value = loc[1]
    else:
        loc_value = ""
    abs_value = abs(value)
    deg =  int(abs_value)
    t1 = (abs_value-deg)*60
    min = int(t1)
    sec = round((t1 - min)* 60, 5)
    return (deg, min, sec, loc_value)


def change_to_rational(number):
    f = Fraction(str(number))
    return (f.numerator, f.denominator)


def set_gps_location(lat, lng):
    lat_deg = to_deg(lat, ["S", "N"])
    lng_deg = to_deg(lng, ["W", "E"])

    exiv_lat = (change_to_rational(lat_deg[0]), change_to_rational(lat_deg[1]), change_to_rational(lat_deg[2]))
    exiv_lng = (change_to_rational(lng_deg[0]), change_to_rational(lng_deg[1]), change_to_rational(lng_deg[2]))

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: lat_deg[3],
        piexif.GPSIFD.GPSLatitude: exiv_lat,
        piexif.GPSIFD.GPSLongitudeRef: lng_deg[3],
        piexif.GPSIFD.GPSLongitude: exiv_lng,
    }

    return gps_ifd

def report_error(message, filename, exception, isConfig = False):
    time_s = time.strftime('%Y%m%d%H%M%S')
    logging.error(f"{time_s}: {message}")
    logging.error(f"location:{filename}")
    logging.error(f"exception: {str(exception)}")
    logging.error("====================================================")
    if not isConfig:
        try:
            if not(os.path.exists(error_pile)):
                os.mkdir(error_pile)
            shutil.move(filename, error_pile + time_s + '_' + os.path.basename(filename) )
        except Exception as ex:
            logging.error("Could not create error pile directory or move the error file")
            logging.error(str(ex))


# runs 24/7 untill manually stoped (has no breaks out of the loop)
while True:
    all_lines = []
    try:
        # Creates a dictionary with all the CSV line objects
        with open(config_path, 'r') as read_obj:
            csv_reader = reader(read_obj)
            header = next(csv_reader)
            if header != None:
                for row in csv_reader:
                    line = {
                        windows_server_folder : row[0],
                        destination_folder : row[1],
                        size : row[2],
                        text : row[3],
                        font : row[4],
                        font_size : row[5],
                        name_prefix : row[6],
                        latitude : row[7],
                        longitude :row[8]
                    }

                    all_lines.append(line)
        logging.info(f"Lines read: {len(all_lines)}")
    except Exception as ex:
        report_error("could not read the config file", config_path, ex, True)
        break

    line_counter = 1
    for entry in all_lines:
        logging.info(f"Starting to process line nr {line_counter}.")

        try:
            # Gets all images from provided directory
            images = [f.path for f in os.scandir(entry[windows_server_folder]) if f.path.endswith(extension)]
        except Exception as ex:
            report_error("failed to get all images from directory", f"Line: {line_counter}", ex, True)
            line_counter += 1
            continue

        try:
            # Creates a tuple with diemnsions for resizing
            dimensions = tuple(map(int, entry[size].split(dimension_splitter)))
        except Exception as ex:
            report_error("failed create dimension tuple", f"Line: {line_counter}", ex, True)
            line_counter += 1
            continue


        try:
            if not entry[font] in fonts:
                fonts[entry[font]] = ImageFont.truetype(entry[font]+'.ttf', int(entry[font_size]))
        except Exception as ex:
            report_error("failed to get font", f"Line: {line_counter}", ex, True)
            line_counter += 1
            continue


        counter = 1

        for image in images:
            if counter == 11:
                break
            logging.info(f"Processing image{image}")
            # The new file name
            file_name = f'{entry[name_prefix]}_{counter:0>4}{extension}'
            full_old_image_path = os.path.join(entry[windows_server_folder],file_name)
            
            # Reads image for edditing
            with Image.open(image) as img:

                try:
                    # Resize
                    img = img.resize(dimensions, resample=Image.Resampling.LANCZOS)
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed to resize image", image, ex)
                    continue


                try:
                    # Gets exif data
                    exif_dict = piexif.load(img.info['exif'])
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed to read exif data", image, ex)
                    continue

                try:
                    # Strips unneded exif data
                    exif_dict['0th'] = {}
                    exif_dict['1st'] = {}
                    exif_dict['Interop'] = {}
                    exif_dict['Exif'] = {}
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed to strip exif data", image, ex)
                    continue

                try:
                    # Sets the provided coordinates in exif data
                    exif_dict = {'GPS' : set_gps_location(float(entry[latitude]),float(entry[longitude]))}
                    exif_bytes = piexif.dump(exif_dict)
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed to save gps exif data", image, ex)
                    continue

                try:
                    # Adds watermark
                    draw = ImageDraw.Draw(img)
                    _, _, w, h = draw.textbbox((0, 0), entry[text], font=fonts[entry[font]])
                    draw.text(((dimensions[0]-w)/2, (dimensions[1]-h)), entry[text], fill=watermark_fill, font=fonts[entry[font]]) 
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed draw a textbox", image, ex)
                    continue


                try:
                    # Saves the new image
                    img.save(full_old_image_path, quality = 75, exif = exif_bytes)
                except Exception as ex:
                    img.close()
                    os.remove(image)
                    report_error("failed to save image", image, ex)
                    continue

                counter += 1

            try:
                # Uploads the file to dropbox
                path = Path(file_name)
                timestamp = time.strftime('%Y%m%d%H%M%S')
                new_name = f"{path.stem}_{timestamp}{path.suffix}"
                destination_path = "{0}\\\\{1}".format(entry[destination_folder],new_name)
                # Checks if the directory exists if not then creates it
                if not os.path.exists(entry[destination_folder]):
                    os.mkdir(entry[destination_folder])
                shutil.copy(full_old_image_path, destination_path)
            except Exception as e:
                report_error("failed to upload to dropbox", image, e)
                os.remove(os.path.join(entry[windows_server_folder],file_name))
                continue

            try:
                # Removes the image from server directory
                os.remove(full_old_image_path)
                os.remove(image)
            except Exception as ex:
                report_error("failed to delete original photos", image, ex)
                continue
            
            logging.info(f"finished processing: {image}")
        logging.info(f"finished line number: {line_counter}.")
        line_counter += 1