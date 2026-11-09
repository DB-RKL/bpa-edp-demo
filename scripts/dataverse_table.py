"""Create the custom table new_bpaquote (opportunity stand-in) in the Dataverse Developer environment."""
import json, subprocess, urllib.request, urllib.error

ORG = "https://YOUR-ORG.crm.dynamics.com"
TN = "<CORP_TENANT_ID>"
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", TN, "--resource", ORG, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
HDR = {"Authorization": "Bearer " + tok, "Content-Type": "application/json", "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json"}


def call(method, path, body=None):
    r = urllib.request.Request(ORG + "/api/data/v9.2/" + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=HDR)
    try:
        x = urllib.request.urlopen(r); return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def label(t):
    return {"@odata.type": "Microsoft.Dynamics.CRM.Label", "LocalizedLabels": [{"@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel", "Label": t, "LanguageCode": 1033}]}


ent = {"@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata", "SchemaName": "new_bpaquote", "DisplayName": label("BPA Quote"),
       "DisplayCollectionName": label("BPA Quotes"), "Description": label("Synthetic bulk annuity quote opportunities for the BPA EDP demo"),
       "OwnershipType": "UserOwned", "HasActivities": False, "HasNotes": False, "PrimaryNameAttribute": "new_name",
       "Attributes": [{"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "AttributeType": "String", "AttributeTypeName": {"Value": "StringType"},
                       "SchemaName": "new_name", "IsPrimaryName": True, "RequiredLevel": {"Value": "SystemRequired"}, "MaxLength": 200, "DisplayName": label("Quote name")}]}
print("table", call("POST", "EntityDefinitions", ent))

attrs = [
    {"@odata.type": "Microsoft.Dynamics.CRM.DecimalAttributeMetadata", "SchemaName": "new_estimatedvalue_gbp_m", "DisplayName": label("Estimated value (GBP m)"), "Precision": 2, "MinValue": 0, "MaxValue": 100000, "RequiredLevel": {"Value": "None"}},
    {"@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata", "SchemaName": "new_closedate", "DisplayName": label("Estimated close date"), "Format": "DateOnly", "RequiredLevel": {"Value": "None"}},
    {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "SchemaName": "new_stage", "DisplayName": label("Stage"), "MaxLength": 50, "RequiredLevel": {"Value": "None"}},
    {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata", "SchemaName": "new_state", "DisplayName": label("State"), "MaxLength": 20, "RequiredLevel": {"Value": "None"}},
]
for a in attrs:
    print(a["SchemaName"], call("POST", "EntityDefinitions(LogicalName='new_bpaquote')/Attributes", a)[0])

rel = {"@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata", "SchemaName": "new_account_bpaquote", "ReferencedEntity": "account", "ReferencedAttribute": "accountid",
       "ReferencingEntity": "new_bpaquote", "CascadeConfiguration": {"Assign": "NoCascade", "Delete": "RemoveLink", "Merge": "NoCascade", "Reparent": "NoCascade", "Share": "NoCascade", "Unshare": "NoCascade"},
       "Lookup": {"@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata", "SchemaName": "new_accountid", "DisplayName": label("Scheme (account)"), "RequiredLevel": {"Value": "None"}}}
print("relationship", call("POST", "RelationshipDefinitions", rel)[0])
print("publish", call("POST", "PublishAllXml", {})[0])
