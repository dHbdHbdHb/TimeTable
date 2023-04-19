
import json
import requests
import pandas as pd
import re
import time
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import os, glob
import time
import logging
import subprocess
from waveshare_epd import epd7in5_V2
#Set up the GPIO pin
import RPi.GPIO as GPIO
button_pin = 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


api_key = 'da56733a-6d62-4da1-9d2f-4e882d46478b'

stops_dict = {
    '16121' : 5, # Portola Dr & Teresita Blvd
    '15255' : 5, #Laguna Honda & Ulloa
    '15254' : 4, # 43 going the other way
    '15834' : 6, # 44 going the other way
    '16113' : 5, #48 towards ocean
    '16937' : 7, #Woodside towards Forest Hill
    '16938' : 7, #Woodside towards Glen Park
    '16669' : 3, #Evelyn Way towards Forest Hill
    '16665' : 2 #Evelyn Way towards Glen Park/Mission
}

routes = ['36','36','43', '43', '44', '44', '48','48', '52', '52', 'LBUS','LBUS']
destinations = ['Forest Hill Station', 
            'Valencia + Mission', 
            'Fort Mason', 
            'Munich + Geneva', 
            'Bayview', 
            'California + 6th Ave', 
            '3rd St + 20th St', 
            'Great Highway',
            'Forest Hill Station', 
            'Persia + Prague', 
            'Ferry Plaza', 
            'SF Zoo'
            ]

class api_511:
    
    def __init__(self, api_key):
        self.api_key = api_key
    
    def get_request(self, url, params):
        try:
            response = requests.get(
                url = url,
                params = {
                    'api_key': self.api_key,
                    **params
                }
            )
            decoded = response.content.decode('utf-8-sig') # strip byte order mark from response
            #print(api_key)
            return json.loads(decoded)
        except:
            self.api_key = 'd9a97f78-8ea2-4221-a834-782930d8cd5b' #sienna's API key lol
            response = requests.get(
                url = url,
                params = {
                    'api_key': self.api_key,
                    **params
                }
            )
            decoded = response.content.decode('utf-8-sig') # strip byte order mark from response
            #print("api key used: " + api_key)
            return json.loads(decoded)      
    
    def get_stops(self, operator_id='SF'):
        response = self.get_request(
            url = 'http://api.511.org/transit/stops',
            params = {
                'format': 'json',
                'operator_id': operator_id
            }
        )
        stop_list = response['Contents']['dataObjects']['ScheduledStopPoint']
        stop_df = pd.DataFrame([
            {
                'stop_id': d['id'],
                'name': d['Name'],
                'longitude': d['Location']['Longitude'],
                'latitude': d['Location']['Latitude'],
                'url': d['Url'],
                'stop_type': d['StopType']
            } for d in stop_list
        ])
        
        return stop_df
    
    def get_stop_monitoring(self, stop_code, operator_id='SF'):
        response = self.get_request(
            url = 'http://api.511.org/transit/StopMonitoring',
            params = {
                'format': 'json',
                'agency': operator_id,
                #'route': route,  doesn't seem to make any difference
                'stopCode': stop_code
            }
        )
        
        monitor_list = response['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']
        monitor_df = pd.DataFrame([
            {
                'timestamp': d['RecordedAtTime'],
                'line': d['MonitoredVehicleJourney']['LineRef'],
                'line_name': d['MonitoredVehicleJourney']['PublishedLineName'],
                'origin_stop_id': d['MonitoredVehicleJourney']['OriginRef'],
                'origin_stop_name': d['MonitoredVehicleJourney']['OriginName'],
                'destination_stop_id': d['MonitoredVehicleJourney']['DestinationRef'],
                'destination_stop_name': d['MonitoredVehicleJourney']['DestinationName'],
                'monitored_stop_id': d['MonitoredVehicleJourney']['MonitoredCall']['StopPointRef'],
                'monitored_stop_name': d['MonitoredVehicleJourney']['MonitoredCall']['StopPointName'],
                'is_monitored': d['MonitoredVehicleJourney']['Monitored'],
                'vehicle_longitude': d['MonitoredVehicleJourney']['VehicleLocation']['Longitude'],
                'vehicle_latitude': d['MonitoredVehicleJourney']['VehicleLocation']['Latitude'],
                'aimed_arrival_time': d['MonitoredVehicleJourney']['MonitoredCall']['AimedArrivalTime'],
                'expected_arrival_time': d['MonitoredVehicleJourney']['MonitoredCall']['ExpectedArrivalTime'],
            } for d in monitor_list
        ])
        
        return monitor_df

def format_time_delta(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    secs_in_a_min = 60
    minutes, seconds = divmod(seconds, secs_in_a_min)
    if seconds >= 30:
        minutes = minutes + 1
    time_fmt = f"{minutes}" + " min" #f"{minutes}:{seconds:02d}"
    return time_fmt

def format_time(df, row, col):
    time = datetime.strptime(re.subn('[T]', ' ', df.at[row,col])[0].replace('Z',''),'%Y-%m-%d %H:%M:%S')
    return time

def color_tag(val, stop_id):
    green_time = 8 
    red_time = 0
    walking_time = stops_dict.get(stop_id) #stops_dict["monitored_stop_id"]
    val = format_time_delta(val)
    etd = int(val.split()[0])
    if (etd - walking_time) >= green_time:
        return val + ":B"
        #append B?
    elif (etd - walking_time) < green_time and (etd - walking_time) > red_time:
        return val + ":G"
        #append G
    elif (etd - walking_time) <= red_time:
        return val + ":R"
        #append R
    else:
        return val + "error"

def filter_by_time(df):
    df_logger = logging.getLogger('dataframe')
    df_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    file_handler = logging.FileHandler('dataframe.log')
    file_handler.setFormatter(formatter)
    df_logger.addHandler(file_handler)
    try:
        #filter out all 36s at stop codes 16938 and 16937
        df = df.loc[(df['line'] != '36') | ((df['line'] == '36') & (df['monitored_stop_id'].isin(['16669', '16665'])))].reset_index(drop = True)
        delta = []
        for i in range(df.shape[0]):
            #Some reformatting of objs/strings in df to be in datetime format
            timestamp = datetime.utcnow()
            first_arrival = format_time(df, i, 'expected_arrival_time')
            delta.append(first_arrival - timestamp)
        df["time_till_departure"] = delta
        df["time_till_departure"] = df.apply(lambda x: color_tag(x['time_till_departure'], x['monitored_stop_id']), axis = 1)
        df.sort_values(['line','destination_stop_name'], inplace=True, ignore_index=True)
    except KeyError as e:
        logging.error(f"KeyError occurred while filtering DataFrame: {e}")
        logging.error(f"DataFrame contents: {df.to_string()}")
        raise      
    return df.reset_index(drop = True)

def relevant_format(df):
    df = filter_by_time(df)
    pivot_df = pd.pivot_table(df, 
                              values = "time_till_departure", 
                              index=["line","destination_stop_name"], 
                              columns=df.groupby(['line',"destination_stop_name"]).cumcount(),
                              aggfunc=lambda x: ' '.join(x)
                              )
    pivot_df.columns = [f"Arrival {i}" for i in range(1, len(pivot_df.columns)+1)]
    pivot_df = pivot_df.reset_index()
    pivot_df = pivot_df.rename(columns={'line': 'Route', 'destination_stop_name': 'Destination', 'Arrival 1': 'Next Arrival'})
    pivot_df = pivot_df.fillna("No Next Arrival")
    #make display ready route names
    pivot_df = pivot_df.replace({"Hudson Ave & 3rd St": 'Bayview', 'Dublin St & La Grande Ave': 'Glen Park', \
                                 'Lower Great Hwy & Rivera St': 'Great Hwy', '20th St & 3rd St': 'The Mission',\
                                 'California St & 6th Ave': 'The Richmond', 'Munich St & Geneva Ave': 'City College',\
                                  'Laguna Honda Blvd/Forest Hill Sta': 'Forest Hill', \
                                  'Valencia St & Mission St': 'The Mission', 'Marina Blvd & Laguna St': 'Marina',\
                                  'Jones St & Beach St': "Downtown", "Wawona/46th Ave /Sf Zoo": 'SF Zoo',\
                                  "Steuart St & Mission St": 'Embarcadero', "San Jose Ave & Geneva Ave" : 'Baloboa Park'
                                          })
    routes = pivot_df['Route'].tolist()
    destinations = pivot_df['Destination'].tolist()
    column_names=['Route', 'Destination', 'Next Arrival', '2nd Arrival', '3rd Arrival']
    empty_cols = pd.DataFrame(columns=column_names[2:])          
    clean_df = pd.DataFrame({'Route':routes, 'Destination': destinations})
    clean_df = pd.concat([clean_df, empty_cols], axis=1)
    clean_df[['Next Arrival', '2nd Arrival', '3rd Arrival']] = \
        pivot_df.loc[:, ~pivot_df.columns.isin(['Route', 'Destination'])].iloc[:, :3].values
    return clean_df

def make_image(df):
    #Set the fonts and header size
    font_size = 23
    font= ImageFont.truetype('fonts/DIN Alternate Bold.ttf', font_size)
    font_direction= ImageFont.truetype('fonts/Trebuchet MS Bold.ttf', 20)
    font_header = ImageFont.truetype('fonts/SFCompact.ttf', 20)
    font_route = ImageFont.truetype('fonts/SFCompact.ttf', 35)
    font_single_route = ImageFont.truetype('fonts/SFCompact.ttf', 30)
    font_update= ImageFont.truetype('fonts/DIN Alternate Bold.ttf', 18)
    padding = 10
    header_space = 60

    # Create the image
    image_width = 800
    image_height = 480 
    cell_width = image_width/5
    cell_height = ((image_height - header_space)/(len(df)))
    image = Image.new("RGB", (image_width, image_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Draw the table headers
    x = 0
    y = 0
    for header in df.columns:
        draw.rectangle((x, y , x + cell_width, y + header_space), fill=(194, 136, 74), outline=(0, 0, 0))
        draw.text((x + padding, y + padding), header, font=font_header, fill=0)
        x += cell_width  # adjust the column width
    
    #Draw background cell colors
    for i, row in df.iterrows():
        x = 0
        for j, val in enumerate(row):
            y = (cell_height) * (i-1) +header_space
            if j >= 1:
                #Alternate gray cells
                if i%2 == 1:
                    draw.rectangle((x, y + cell_height , x + cell_width, y + (cell_height*2)), fill=(211, 211, 211), outline= (0,0,0))
            x += cell_width
            # Draw vertical lines between columns
            draw.line((x ,y , x ,y+(cell_height*2)), fill=(0,0,0), width=1)

    #Draw first column and routes 
    y = header_space
    for i, row in df.iterrows():
        x = 0
        for j, val in enumerate(row):
            if (df['Route'] == val).sum() == 1: #The first column if there is a single instance of the route
                draw.rectangle((x, y, x + cell_width, y + cell_height), fill=(150, 94, 209), outline=(0, 0, 0))
                draw.text((x + 20, y + padding/2), str(val), font=font_single_route, fill=(0, 0, 0))
                y = y + (cell_height)
            if i%2 == 1 and (df['Route'] == val).sum() == 2: #The first column if there are two instances of the route
                draw.rectangle((x, y, x + cell_width, y + cell_height*2), fill=(150, 94, 209), outline=(0, 0, 0))
                draw.text((x + 15, y + padding), str(val), font=font_route, fill=(0, 0, 0))
                y = y + (cell_height * 2)

    #Fill in values
    for i, row in df.iterrows():
        x = 0
        for j, val in enumerate(row):
            y = (cell_height) * (i) + header_space
            # y = (cell_height) * (i-1) +header_space
            if j >= 1:
                #condition to change color based off whether should leave or not
                if j >= 2 and val.split()[0] == "No":
                    draw.text((x + 3, y + padding), val, font=font, fill='grey') 
                elif j >= 2 and val.split(":")[1] == "G": #and int(val.split()[0]) >= 4 and int(val.split()[0]) <= 15: ### something like str(val.split(":")[1] == G
                    draw.text((x + 3, y  + padding), val.split(":")[0], font=font, fill='black') #Write in green text
                elif j >= 2 and val.split(":")[1] == "R": #int(val.split()[0]) <= 4: ### something like str(val).split(":")[1] == R
                    draw.text((x + 3, y  + padding), (val.split(":")[0] + " !"), font=font, fill=(255, 25, 37))
                elif j>=2:
                    draw.text((x + 3, y  + padding), val.split(":")[0], font=font, fill='grey')
                else:
                    draw.text((x + 3, y  + padding), val.split(":")[0], font=font_direction, fill='black' )
            x += cell_width


    #line separating headers from data
    draw.line((0, header_space, image_width, header_space), fill=(0, 0, 0), width=10)
    
    #Update time:
    current_time = datetime.now()
    current_time = current_time.strftime("%-H:%M")
    draw.text((3, 35), "Updated at " + str(current_time), font=font_update, fill=(0,0,0))
    print("Updated at " + str(current_time))

    # save the image
    unique_time = datetime.now()
    unique_time = unique_time.strftime("%-m_%-d-%H_%-M")
    for filename in glob.glob("static/images/display*"):
        os.remove(filename)
    image.save("static/images/display"+ unique_time + ".png")
    #display image and protect screen
    print("init and Clear")
    epd.init()
    epd.Clear()
    h_image = Image.new('1', (epd.width, epd.height), 255)
    h_image.paste(image, (0,0))
    epd.display(epd.getbuffer(h_image))
    epd.sleep()
    # return the image
    return image



logger = logging.getLogger('main')
logger.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
file_handler = logging.FileHandler('main.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

try:
    logging.info("epd7in5_V2 Demo")
    epd = epd7in5_V2.EPD()
    while(True):
        api = api_511(api_key)
        local_df = pd.DataFrame()
        for key in stops_dict:
           local_df = pd.concat([local_df, api.get_stop_monitoring(key)], ignore_index=True)
        relevant_df = relevant_format(local_df)
        make_image(relevant_df)
        if datetime.now().strftime('%H') == '03':
            print('Clearing screen to avoid burn-in.')
            epd.init()
            epd.Clear()
            time.sleep(600)
        GPIO.wait_for_edge(button_pin, GPIO.FALLING, timeout=420000)
        
except KeyboardInterrupt:
    GPIO.cleanup()
    print("Clear...")
    logging.info("Clear...")
    epd.init()
    epd.Clear()

except IOError as e:
    print("error")
    logging.info(e)
    epd.sleep()

except Exception as e:
    print("Poop... you have an error and should check the logs.  Program will restart in an hour")
    logging.error(f"Error occurred: {str(e)}")
    logging.exception("Traceback:")
    epd.init()
    epd.Clear()
    # e_image = "static/images/error.png"   #Have to create this error image
    # epd.display(epd.getbuffer(e_image))   #Might need to save/create more like above

    # Wait for one hour before restarting the program
    time.sleep(3600)
     # Restart the program using subprocess
    subprocess.Popen(['python', 'main.py'])