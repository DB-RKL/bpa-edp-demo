import json,urllib.request,urllib.parse,os,time,random,csv,io
d=json.load(open(os.path.expanduser("~/.bpa-edp/corp/sp.json")))
def tok(scope):
    data=urllib.parse.urlencode({"grant_type":"client_credentials","client_id":d["appId"],"client_secret":d["password"],"scope":scope}).encode()
    return json.load(urllib.request.urlopen(f"https://login.microsoftonline.com/{d['tenant']}/oauth2/v2.0/token",data))["access_token"]
def call(method,url,t,body=None,raw=None,hdr=None):
    h={"Authorization":"Bearer "+t}; h.update(hdr or {})
    data=raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if body is not None: h["Content-Type"]="application/json"
    r=urllib.request.Request(url,data=data,method=method,headers=h)
    try:
        resp=urllib.request.urlopen(r); b=resp.read().decode(); return resp.status,(json.loads(b) if b.startswith("{") else b),resp.headers
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:400],e.headers
F="https://api.fabric.microsoft.com/v1"; ft=tok("https://api.fabric.microsoft.com/.default")
CAP="<FABRIC_CAPACITY_ID>"
s,r,_=call("GET",F+"/workspaces",ft); ws=next((w for w in r["value"] if w["displayName"]=="bpa-edp-demo-corp"),None)
W=ws["id"]
if not ws.get("capacityId"):
    print("assign",call("POST",f"{F}/workspaces/{W}/assignToCapacity",ft,{"capacityId":CAP})[:2])
s,r,_=call("GET",f"{F}/workspaces/{W}/lakehouses",ft); lh=next((l for l in r["value"] if l["displayName"]=="bpa_edp"),None)
if not lh:
    s,lh,h=call("POST",f"{F}/workspaces/{W}/lakehouses",ft,{"displayName":"bpa_edp"}); print("lh",s,lh)
    if s==202:
        time.sleep(20); s,r,_=call("GET",f"{F}/workspaces/{W}/lakehouses",ft); lh=next(l for l in r["value"] if l["displayName"]=="bpa_edp")
L=lh["id"]; print("workspace",W,"lakehouse",L)
random.seed(7); out=io.StringIO(); w=csv.writer(out)
w.writerow(["quote_id","scheme_name","quote_date","members","liability_gbp_m","discount_rate_pct","longevity_basis","quoted_premium_gbp_m","premium_pct_of_liability","outcome"])
names=["Aldwych","Brentford","Carrow","Delamere","Eastgate","Fenwick","Grafton","Hollin","Ingrams","Jesmond"]
for i in range(1,241):
    liab=round(random.uniform(20,900),1); pct=round(random.uniform(97,112),1)
    w.writerow([f"Q{i:05d}",f"{random.choice(names)} Pension Scheme",f"202{random.randint(3,6)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
      random.randint(150,12000),liab,round(random.uniform(4.2,5.6),2),random.choice(["S3PA CMI2023","S4PA CMI2023","Bespoke VitaCurves"]),round(liab*pct/100,1),pct,random.choice(["won","lost","withdrawn"])])
dt=tok("https://storage.azure.com/.default"); base=f"https://onelake.dfs.fabric.microsoft.com/{W}/{L}/Files/edp_historical_quotes.csv"
b=out.getvalue().encode()
print("create",call("PUT",base+"?resource=file",dt,raw=b"",hdr={"Content-Length":"0"})[0])
print("append",call("PATCH",base+f"?action=append&position=0",dt,raw=b,hdr={"Content-Type":"application/octet-stream"})[0])
print("flush",call("PATCH",base+f"?action=flush&position={len(b)}",dt,raw=b"",hdr={"Content-Length":"0"})[0])
s,r,h=call("POST",f"{F}/workspaces/{W}/lakehouses/{L}/tables/edp_historical_quotes/load",ft,
  {"relativePath":"Files/edp_historical_quotes.csv","pathType":"File","mode":"Overwrite","formatOptions":{"format":"Csv","header":True,"delimiter":","}})
print("load",s,r)
json.dump({"workspace":W,"lakehouse":L},open(os.path.expanduser("~/.bpa-edp/corp/fabric.json"),"w"))
