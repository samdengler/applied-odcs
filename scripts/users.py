"""Creates Alice and Bob in the user pool with the one demo password from
APPLIED_ODCS_PASSWORD, permanent.  Safe to run again: an existing user
gets the password reset."""

import os

import boto3

# The policy file has no users and the policies read no role: the token's
# username is the caller, and each user is an employee with a record.
USERS = ("alice", "bob")


def main() -> None:
    pool = os.environ["USER_POOL_ID"]
    password = os.environ["APPLIED_ODCS_PASSWORD"]
    idp = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    for user in USERS:
        try:
            idp.admin_create_user(
                UserPoolId=pool, Username=user, MessageAction="SUPPRESS",
                UserAttributes=[{"Name": "email", "Value": f"{user}@example.com"},
                                {"Name": "email_verified", "Value": "true"}])
            created = "created"
        except idp.exceptions.UsernameExistsException:
            created = "exists"
        idp.admin_set_user_password(UserPoolId=pool, Username=user, Password=password, Permanent=True)
        print(f"{user:6} {created}")


if __name__ == "__main__":
    main()
