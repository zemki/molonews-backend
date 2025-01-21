import poplib
pop3server = 'wp1049046.mail.server-he.de'
username = 'wp1049046-newsletter'
password = '7qSt6pkIN'
pop3server = poplib.POP3_SSL(pop3server) # open connection
#pop3server.set_debuglevel(2)
print (pop3server.getwelcome()) #show welcome message
pop3server.user(username)
pop3server.pass_(password)
pop3info = pop3server.stat() #access mailbox status
mailcount = pop3info[0] #toral email
print("Total no. of Email : " , mailcount)
print ("\n\nStart Reading Messages\n\n")
for i in range(mailcount):
    for message in pop3server.retr(i+1)[1]:
        print (message)
pop3server.quit()

# E-Mail schön importieren
# HTML Zeug anwenden
# E-Mail als Artikel importieren mit Subject als Title
# 