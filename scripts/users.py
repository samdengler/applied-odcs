"""Creates Alice, Carol, and Dave in the user pool with the one demo
password from APPLIED_ODCS_PASSWORD, permanent, and their groups.  Safe
to run again: an existing user gets the password reset and the groups
re-added."""

import os

import boto3

USERS = {"alice": [], "carol": ["support", "employee"], "dave": ["finance", "employee"]}


def main() -> None:
    pool = os.environ["USER_POOL_ID"]
    password = os.environ["APPLIED_ODCS_PASSWORD"]
    idp = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    for user, groups in USERS.items():
        try:
            idp.admin_create_user(
                UserPoolId=pool, Username=user, MessageAction="SUPPRESS",
                UserAttributes=[{"Name": "email", "Value": f"{user}@example.com"},
                                {"Name": "email_verified", "Value": "true"}])
            created = "created"
        except idp.exceptions.UsernameExistsException:
            created = "exists"
        idp.admin_set_user_password(UserPoolId=pool, Username=user, Password=password, Permanent=True)
        for group in groups:
            idp.admin_add_user_to_group(UserPoolId=pool, Username=user, GroupName=group)
        print(f"{user:6} {created:8} groups: {', '.join(groups) or 'none'}")


if __name__ == "__main__":
    main()
