import requests, time, json
import pyzbar.pyzbar
from PIL import Image

TELEGRAM_TOKEN = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

TELEGRAM_ENDPOINT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

data = {}
boot_time = -1 
last_dump = -1

def send_message(chat_id, message):
        payload = {'chat_id': chat_id, 'text': message}
        requests.post(TELEGRAM_ENDPOINT + '/sendMessage', data=payload)



def get_last_stations(user_id):
        endpoint = "https://apigateway.tembici.com.br/engagement/user/trips/history/"
        headers = {'client-id': data[user_id]['client-id']}
        headers['key'] = data[user_id]['client-id']
        headers['authorization'] = "Bearer " + data[user_id]['access_token']
        payload = '{"page":1,"limit":40,"list_open_trips":false}'
        response = requests.post(endpoint, data=payload, headers=headers).json()['results']
        data[user_id]['last_stations'] = []
        for trip in response:
                a = trip['started_station']['id']
                b = trip['ended_station']['id']
                if a not in data[user_id]['last_stations']:
                        data[user_id]['last_stations'].append(a)
                if b not in data[user_id]['last_stations']:
                        data[user_id]['last_stations'].append(b)



def auth_user(chat_id, user_id, email, password):
        endpoint = "https://temflow.tembici.com.br/api/legacy/account/signin"
        headers = {'client-id': data[user_id]['client-id']}
        payload = f'{{"login":"{email}","password":"{password}"}}'
        response = requests.post(endpoint, data=payload, headers=headers).json()
        text = json.dumps(response, indent=4, ensure_ascii=False)
        print(f"{user_id} auth attempt:\n{text}")
        if 'refresh_token' not in response.keys():
                send_message(chat_id, f"authentication problems 🙁\n\n{text}")
                return
        data[user_id]['refresh_token'] = response['refresh_token']
        data[user_id]['access_token'] = response['access_token']
        data[user_id]['last_refresh'] = time.time()
        send_message(chat_id, "authentication successful 🙂")
        get_last_stations(user_id)



def refresh_token(chat_id, user_id):
        if time.time() - data[user_id]['last_refresh'] < 1800:
                return
        endpoint = "https://temflow.tembici.com.br/api/builtin/token/refresh_session"
        headers = {'client-id': data[user_id]['client-id']}
        payload = f'{{"refresh_token":"{data[user_id]["refresh_token"]}"}}'
        response = requests.post(endpoint, data=payload, headers=headers).json()
        text = json.dumps(response, indent=4, ensure_ascii=False)
        print(f"{user_id} token refresh attempt:\n{text}")
        if 'refresh_token' not in response.keys():
                send_message(chat_id, f"token refresh problems 🙁\n\n{text}")
                return
        data[user_id]['refresh_token'] = response['refresh_token']
        data[user_id]['access_token'] = response['access_token']
        data[user_id]['last_refresh'] = time.time()
        get_last_stations(user_id)



def unlock(chat_id, user_id, code):
        refresh_token(chat_id, user_id)
        endpoint = endpoint = f"https://apigateway.tembici.com.br/system/bike/unlock/qrcode?bike={code}"
        code = code.upper()
        if code.isdigit() and int(code) <= 9999:
                endpoint = f"https://apigateway.tembici.com.br/system/3/station/{code}/rent"
        headers = {"key": data[user_id]['client-id'], "authorization": "Bearer " + data[user_id]['access_token']}
        response = requests.get(endpoint, headers=headers).json()
        text = json.dumps(response, indent=4, ensure_ascii=False)
        print(f"{user_id} unlock attempt with code {code}:\n{text}")
        send_message(chat_id, text)



def decode_qr(chat_id, user_id, file_id):
        refresh_token(chat_id, user_id)
        endpoint = TELEGRAM_ENDPOINT + "/getFile?file_id=" + file_id
        file_path = requests.get(endpoint).json()['result']['file_path']
        endpoint = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_path
        content = pyzbar.pyzbar.decode(Image.open(requests.get(endpoint, stream=True).raw))
        print(f"QR decoded content: {content}")
        code = content[0].data.decode().split('=')[-1]
        return code


def list_stations(chat_id, user_id, stations, distances):
        refresh_token(chat_id, user_id)
        headers = {"x-api-key": data[user_id]['x-api-key']}
        details = ""
        for (station_id, distance) in zip(stations, distances):
                endpoint = f"https://api.tembici.com/stations/v1/3/get/{station_id}"
                response = requests.get(endpoint, headers=headers).json()
                if 'station' not in response.keys():
                        continue
                station = response['station']
                if str(station_id) not in station['name']:
                        aux = station['name'].split(' ', 1)
                        details += f"{station['id']}* {aux[1]}"
                else:
                        details += f"{station['name']}"
                if distance != "0m":
                        details += f" ({distance})"
                details += ":   "
                if not station['is_online']:
                        details += "offline,  "
                details += f"{station['status']['available']['mechanical']} 🚲 / "
                details += f"{station['status']['docks']} ⚓\n"
                # single station request
                if len(stations) == 1 and distance == "0m":
                        details += f"\n{station['address']['str']}"
                        send_message(chat_id, details)
                        details = "Nearby stations:\n\n"
                        nearby_ids = [ neighbour['id'] for neighbour in response['nearby'] ]
                        nearby_dists = [ neighbour['distance'] for neighbour in response['nearby'] ]
                        details += list_stations(chat_id, user_id, nearby_ids, nearby_dists)
                        send_message(chat_id, details)
                        return
        # a neighnourhood request
        if distances[0] != "0m":
                return details
        # multiple stations request
        send_message(chat_id, details)



def process(msg):
        chat_id = str(msg['chat']['id'])
        user_id = str(msg['from']['id'])
        date = msg['date']
        if date < boot_time:
                return

        if user_id not in data.keys():
                data[user_id] = {
                        'last_msg': -1,
                        'last_refresh' : -1,
                        'refresh_token' : "",
                        'access_token' : "",
                        'client-id' : "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                        'x-api-key': "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                        'last_stations': [],
                }
        if date < data[user_id]['last_msg']:
                return

        data[user_id]['last_msg'] = time.time()

        if 'text' in msg.keys():
                command = msg['text'].lower().split(' ')
                if command[0] == 'login':
                        auth_user(chat_id, user_id, command[1], command[2])
                elif command[0] == 'unlock':
                        unlock(chat_id, user_id, command[1])
                elif command[0] == 'info' and len(command) == 1:
                        list_stations(chat_id, user_id, data[user_id]['last_stations'], ["0m"]*len(data[user_id]['last_stations']))
                elif command[0] == 'info' and len(command) != 1:
                        list_stations(chat_id, user_id, command[1:], ["0m"])
                else:
                        send_message(chat_id, "Unknow command.")
        else:
                file_id = msg['photo'][-1]['file_id']
                code = decode_qr(chat_id, user_id, file_id)
                unlock(chat_id, user_id, code)



def start_bot():
        global last_dump
        global boot_time
        last_dump = time.time()
        boot_time = time.time()
        try:
                with open('data.json') as f:
                        global data
                        data = json.load(f)
        except Exception as e:
                pass

        while True:
                try:
                        time.sleep(0.6)
                        if time.time() - last_dump > 60:
                                with open('data.json', 'w') as f:
                                        json.dump(data, f, indent=4, ensure_ascii=False)
                                last_dump = time.time()
                        endpoint = TELEGRAM_ENDPOINT + '/getUpdates?allowed_updates=message&offset=-50'
                        events = requests.get(endpoint)
                        events = events.json()['result']
                        events.reverse()
                        messages = [ event['message'] for event in events ]
                        for msg in messages:
                                process(msg)
                except Exception as e:
                        print("ERROR:", e)


if __name__ == "__main__":
        start_bot()
