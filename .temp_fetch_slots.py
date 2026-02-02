import requests
r = requests.get('http://127.0.0.1:8001/api/slots/upcoming/', timeout=5)
print('STATUS', r.status_code)
print(r.text[:1000])
