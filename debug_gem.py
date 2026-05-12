import requests, json

session = requests.Session()
landing = session.get(
    'https://bidplus.gem.gov.in/all-bids',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'},
    timeout=15
)
csrf = session.cookies.get('csrf_gem_cookie', '')
print('CSRF:', csrf[:10], '...')

payload = {'page': 1, 'param': {}, 'filter': {}}
data = {
    'payload': json.dumps(payload),
    'csrf_bd_gem_nk': csrf,
}
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Referer': 'https://bidplus.gem.gov.in/all-bids',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
}
r = session.post('https://bidplus.gem.gov.in/all-bids-data', data=data, headers=headers, timeout=15)
print('Status:', r.status_code)
result = r.json()
print('Code:', result.get('code'))
docs = result.get('response', {}).get('response', {}).get('docs', [])
print('Docs count:', len(docs))
if docs:
    print('\nFirst doc keys:', list(docs[0].keys()))
    print('\nFirst doc:')
    print(json.dumps(docs[0], indent=2, ensure_ascii=False)[:2000])
