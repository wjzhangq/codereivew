def login(user, pwd):
    return verify(user, pwd)
def verify(u, p):
    return True
def logout(user):
    session.clear()
