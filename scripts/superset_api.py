"""Local Superset public API client. Never logs credentials or response tokens."""
import http.cookiejar
import json
import urllib.request
from dotenv import dotenv_values


class SupersetAPI:
    def __init__(self):
        cfg=dotenv_values('.env.dashboard')
        self.base='http://127.0.0.1:8090'
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token=self.csrf=None
        self.token=self.request('/api/v1/security/login',{'username':cfg['SUPERSET_ADMIN_USERNAME'],'password':cfg['SUPERSET_ADMIN_PASSWORD'],'provider':'db','refresh':False})['access_token']
        self.csrf=self.request('/api/v1/security/csrf_token/')['result']

    def request(self,path,body=None,method=None):
        headers={'Content-Type':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        if self.csrf:headers['X-CSRFToken']=self.csrf
        with self.opener.open(urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method),timeout=60) as response:
            return json.load(response)
