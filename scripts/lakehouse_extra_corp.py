import json,urllib.request,urllib.parse,os,random,csv,io,time
d=json.load(open(os.path.expanduser("~/.bpa-edp/corp/sp.json"))); f=json.load(open(os.path.expanduser("~/.bpa-edp/corp/fabric.json")))
W,L=f["workspace"],f["lakehouse"]
def tok(scope):
    data=urllib.parse.urlencode({"grant_type":"client_credentials","client_id":d["appId"],"client_secret":d["password"],"scope":scope}).encode()
    return json.load(urllib.request.urlopen(f"https://login.microsoftonline.com/{d['tenant']}/oauth2/v2.0/token",data))["access_token"]
def call(method,url,t,body=None,raw=None,hdr=None):
    h={"Authorization":"Bearer "+t}; h.update(hdr or {})
    data=raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if body is not None: h["Content-Type"]="application/json"
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,data=data,method=method,headers=h)); return r.status
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:300]
ft=tok("https://api.fabric.microsoft.com/.default"); dt=tok("https://storage.azure.com/.default")
def upload(path,b):
    u=f"https://onelake.dfs.fabric.microsoft.com/{W}/{L}/{path}"
    return [call("PUT",u+"?resource=file",dt,raw=b"",hdr={"Content-Length":"0"}),
            call("PATCH",u+"?action=append&position=0",dt,raw=b,hdr={"Content-Type":"application/octet-stream"}),
            call("PATCH",u+f"?action=flush&position={len(b)}",dt,raw=b"",hdr={"Content-Length":"0"})]
def tocsv(rows):
    o=io.StringIO(); csv.writer(o).writerows(rows); return o.getvalue().encode()
random.seed(11)
names=["Aldwych","Brentford","Carrow","Delamere","Eastgate","Fenwick","Grafton","Hollin","Ingrams","Jesmond"]
accts=[(f"a{i:04d}-0000-4000-8000-{i:012d}",f"{names[i%10]} Pension Scheme {i//10+1}",random.choice(["Corporate Trustee","Sponsor","Consultant"]),random.choice(["London","Leeds","Bristol","Glasgow"])) for i in range(1,61)]
# Dataverse-style tables (as a Gen2 dataflow from Dataverse would land them)
dv={
 "dv_account":[["accountid","name","customertypecode","address1_city","createdon"]]+[[a,n,t,c,f"2025-{random.randint(1,12):02d}-{random.randint(1,28):02d}"] for a,n,t,c in accts],
 "dv_opportunity":[["opportunityid","name","parentaccountid","estimatedvalue","estimatedclosedate","statecode","stepname"]]+[[f"o{i:04d}-0000-4000-8000-{i:012d}",f"BPA quote {i}",random.choice(accts)[0],round(random.uniform(20,900),1)*1e6,f"2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}",random.choice(["Open","Won","Lost"]),random.choice(["Qualify","Develop","Propose","Close"])] for i in range(1,181)],
}
for n,rows in dv.items():
    print(n,upload(f"Files/dataverse_landing/{n}.csv",tocsv(rows)))
# SharePoint-style files, as a SharePoint shortcut folder would expose them
sp={"scheme_assumptions.csv":[["scheme","valuation_date","discount_rate_pct","inflation_pct","longevity_table"]]+[[a[1],"2026-03-31",round(random.uniform(4.2,5.6),2),round(random.uniform(2.8,3.6),2),random.choice(["S3PA CMI2023","S4PA CMI2023"])] for a in accts]}
for n,rows in sp.items(): print(n,upload(f"Files/sharepoint_shortcut/{n}",tocsv(rows)))
try:
    import openpyxl
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="Pricing assumptions"
    for r in [["scheme","member_count","avg_pension_gbp","expense_loading_pct"]]+[[a[1],random.randint(150,12000),random.randint(2500,9000),round(random.uniform(0.5,1.5),2)] for a in accts]: ws.append(r)
    bio=io.BytesIO(); wb.save(bio); print("xlsx",upload("Files/sharepoint_shortcut/pricing_assumptions.xlsx",bio.getvalue()))
except ImportError: print("openpyxl missing: xlsx skipped")
for n in dv:
    print("load",n,call("POST",f"https://api.fabric.microsoft.com/v1/workspaces/{W}/lakehouses/{L}/tables/{n}/load",ft,{"relativePath":f"Files/dataverse_landing/{n}.csv","pathType":"File","mode":"Overwrite","formatOptions":{"format":"Csv","header":True,"delimiter":","}}))
