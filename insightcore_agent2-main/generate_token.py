from app.auth import create_access_token

# Data you want inside token
user_data = {
    "sub": "admin",
    "role": "admin"
}

token = create_access_token(user_data)

print("JWT TOKEN:")
print(token)
