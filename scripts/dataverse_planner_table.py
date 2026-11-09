"""Create the Dataverse table new_plannerstep (one row per scheme per step on the way to buyout), with change tracking on and a lookup to account."""
import json, subprocess, urllib.request, urllib.error
ORG = "https://YOUR-ORG.crm.dynamics.com"; TN = "<CORP_TENANT_ID>"
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", TN, "--resource", ORG, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
HDR = {"Authorization": "Bearer " + tok, "Content-Type": "application/json", "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json"}
def call(method, path, body=None):
    r = urllib.request.Request(ORG + "/api/data/v9.2/" + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=HDR)
    try:
        x = urllib.request.urlopen(r, timeout=300); return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:400]
def label(t): return {"@odata.type": "Microsoft.Dynamics.CRM.Label", "LocalizedLabels": [{"@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel", "Label": t, "LanguageCode": 1033}]}
s, b = call("GET", "EntityDefinitions(LogicalName='new_plannerstep')?$select=LogicalName")
if s == 200: print("table already exists"); raise SystemExit
ent = {"@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata", "SchemaName": "new_plannerstep", "DisplayName": label("Planner Step"), "DisplayCollectionName": label("Planner Steps"),
       "Description": label("Steps to move each scheme to buyout (synthetic, for the BPA buy-in demo)"), "OwnershipType": "UserOwned", "HasActivities": False, "HasNotes": False,
       "ChangeTrackingEnabled": True, "PrimaryNameAttribute": "new_name",
       "Attributes": [{"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "AttributeType": "String", "AttributeTypeName": {"Value": "StringType"}, "SchemaName": "new_name",
                       "IsPrimaryName": True, "RequiredLevel": {"Value": "SystemRequired"}, "MaxLength": 200, "DisplayName": label("Step")}]}
print("table", call("POST", "EntityDefinitions", ent)[0])
attrs = [
 {"@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata", "SchemaName": "new_stepno", "DisplayName": label("Step number"), "MinValue": 1, "MaxValue": 20, "RequiredLevel": {"Value": "None"}},
 {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "SchemaName": "new_stepname", "DisplayName": label("Step name"), "MaxLength": 100, "RequiredLevel": {"Value": "None"}},
 {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "SchemaName": "new_stepowner", "DisplayName": label("Step owner"), "MaxLength": 100, "RequiredLevel": {"Value": "None"}},
 {"@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata", "SchemaName": "new_duedate", "DisplayName": label("Due date"), "Format": "DateOnly", "RequiredLevel": {"Value": "None"}},
 {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "SchemaName": "new_status", "DisplayName": label("Status"), "MaxLength": 30, "RequiredLevel": {"Value": "None"}},
]
for a in attrs: print(a["SchemaName"], call("POST", "EntityDefinitions(LogicalName='new_plannerstep')/Attributes", a)[0])
rel = {"@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata", "SchemaName": "new_account_plannerstep", "ReferencedEntity": "account", "ReferencedAttribute": "accountid", "ReferencingEntity": "new_plannerstep",
       "CascadeConfiguration": {"Assign": "NoCascade", "Delete": "RemoveLink", "Merge": "NoCascade", "Reparent": "NoCascade", "Share": "NoCascade", "Unshare": "NoCascade"},
       "Lookup": {"@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata", "SchemaName": "new_accountid", "DisplayName": label("Scheme (account)"), "RequiredLevel": {"Value": "None"}}}
print("relationship", call("POST", "RelationshipDefinitions", rel)[0])
print("publish", call("POST", "PublishAllXml", {})[0])
s, b = call("GET", "EntityDefinitions(LogicalName='new_plannerstep')?$select=ChangeTrackingEnabled,EntitySetName"); print("check:", b[:200])
