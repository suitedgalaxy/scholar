import flask,flask_sock
import pyautogui,keyboard,mouse
from mss import mss as mssScreenshot
from numpy import array as nparray
from cv2 import imencode as imageEncode
import tkinter,tkinter.ttk
import time,json,threading,hashlib,random,dataclasses
from simple_websocket import ConnectionClosed
import socket

directory = '/'.join(__file__.split('\\')[:-1])
flaskServer = flask.Flask(__name__)
flaskServer.secret_key = b'abc18517777dc41919c00e6db57bbdd86fe1938aac23421c4cce48d27d9cd063'
flaskSocket = flask_sock.Sock(flaskServer)

SCPTkWindow = tkinter.Tk()
SCPTkWindow.minsize(100,100)
SCPTkWindow.title('SCP') # Server Control Panel
SCPTkWindow.iconbitmap(f'{directory}/SCP.ico')

tkNotebook = tkinter.ttk.Notebook(SCPTkWindow)
tkNotebook.pack(padx=5, pady=5, expand=True, fill=tkinter.BOTH, anchor='nw')

mainservertab = tkinter.Frame(tkNotebook)
tkNotebook.add(mainservertab,text="Server Details")

tkinter.Label(mainservertab,text=f"IPv4 Address: {socket.gethostbyname(socket.gethostname())}",font=("Arial",15)).pack(anchor='nw')

buttonTab = tkinter.Frame(tkNotebook)
tkNotebook.add(buttonTab,text='Circuit Breaker')

@flaskServer.route('/')
def ss_home(): return flask.send_file(f'{directory}/home.html')
@flaskSocket.route('/')
def ss_home_sock(ws):
	try: user = str(flask.session['User'])
	except KeyError: user = None
	ws.send(json.dumps(user))

class User:
	usersByName = {}
	usersByHash = {}
	hashNumber = 0
	guestNumber = 0
	def __init__(self, username, password=None, userhash=None, registered=True):
		if userhash is None: userhash = User.createUserHash(username)
		self.userHash = userhash
		self.nickname = username
		self.guest = not registered
		User.usersByHash[userhash] = self
		# GAMES
		self.uno = None
		if not registered: return
		self.username = username
		self.password = password
		User.usersByName[username] = self
	@classmethod
	def createUserHash(c, username=''):
		c.hashNumber += 1
		return hashlib.sha256(bytes(username+str(c.hashNumber),'utf8')).digest()
	@classmethod
	def createGuestUser(c):
		c.guestNumber += 1
		return User(f'Guest {c.guestNumber}', registered=False)
	@classmethod
	def loginUser(c, username, password):
		if username not in c.usersByName: return False, None
		user = c.usersByName[username]
		if user.password != password: return False, None
		return True, user

@flaskServer.route('/login',methods=['POST'])
def user_login():
	match, user = User.loginUser(flask.request.form['username'],flask.request.form['password'])
	if match: flask.session['User'] = user.userHash
	return flask.redirect('/')
@flaskServer.route('/guestlogin',methods=['POST'])
def user_guestlogin():
	flask.session['User'] = User.createGuestUser().userHash
	return flask.redirect('/')
@flaskServer.route('/logout',methods=['POST'])
def user_logout():
	userhash = flask.session.pop('User',None)
	if userhash is not None and userhash in User.usersByHash and User.usersByHash[userhash].guest: del User.usersByHash[userhash]
	return flask.redirect('/')

User('Suitedgalaxy','PCP')
User('kieran2007','IDGAF')

@flaskServer.before_request
def ss_before_request():
	userhash = flask.session.get("User")
	if userhash is not None and userhash not in User.usersByHash: return user_logout()
	if userhash is None and flask.request.path[1:] not in ('','favicon.ico','login','guestlogin','logout','signup','user'): return flask.redirect('/')

class RemoteDesktop:
	width,height = tuple(pyautogui.size())
	videoFPS = 1/30
	pressed = set()
	log = []

	_enabled = True
	allowedUser = User.usersByName["Suitedgalaxy"]
	controlButton = tkinter.Button(buttonTab,text='Remote Desktop',command=lambda:RemoteDesktop.toggle())
	controlButton.configure(background='green',activebackground='yellow',height=5,width=20)
	controlButton.pack(anchor='nw',side=tkinter.LEFT)

	@classmethod
	def toggle(c):
		c._enabled = not c._enabled
		c.controlButton.configure(background='green' if c._enabled else 'red')
		if c._enabled: c.reset()
	@classmethod
	def reset(c):
		for _ in c.pressed: keyboard.release(_)
		c.pressed = set()

	@classmethod
	def _manageLog(cls,l):
		cls.log.append(l)
		if len(cls.log)>16: cls.log.pop(0)
	@classmethod
	def mouse_move(c,x,y,w,h,log=True):
		x,y=x*c.width/w,y*c.height/h
		mouse.move(x,y)
		# if log: c._manageLog(f'Mouse: Moved to ({x}, {y})')
		return x,y
	@classmethod
	def mouse_press(c,x,y,w,h,p,b):
		x,y=c.mouse_move(x,y,w,h,False)
		(mouse.press if p else mouse.release)('left' if b==0 else 'right')
		c._manageLog(f'{"Pressed" if p else "Released"} {"Left" if b==0 else "Right"} at ({x}, {y})')
	@staticmethod
	def _keyboard_button_map(b):
		try: return {'ArrowUp':'up','ArrowDown':'down','ArrowLeft':'left','ArrowRight':'right','Meta':'win'}[b]
		except KeyError: return b.lower()
	@classmethod
	def keyboard_press(c,p,b):
		b = c._keyboard_button_map(b)
		try: (c.pressed.add if p else c.pressed.remove)(b)
		except KeyError: pass
		(keyboard.press if p else keyboard.release)(b)
		if p and b=='win': c.keyboard_press(False,b)
		c._manageLog(f'{"Pressed" if p else "Released"} {b}')
	@classmethod
	def image_generator(c):
		with mssScreenshot() as sct:
			while True:
				if not RemoteDesktop._enabled: return
				yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n'+imageEncode('.jpg',nparray(sct.grab({'top':0,'left':0,'width':c.width,'height':c.height})))[1].tobytes()+b'\r\n')
				time.sleep(c.videoFPS)

def remotedesktop_before_request():
	if not RemoteDesktop._enabled: flask.abort(503)
	if User.usersByHash[flask.session['User']] != RemoteDesktop.allowedUser: flask.abort(403)
@flaskServer.route('/remoteDesktop')
def remotedesktop_home():
	remotedesktop_before_request()
	RemoteDesktop.reset()
	return flask.send_file(f'{directory}/remoteDesktop/remotedesktop.html')
@flaskServer.route('/remoteDesktop/video')
def remotedesktop_video():
	remotedesktop_before_request()
	return flask.Response(RemoteDesktop.image_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')
@flaskSocket.route('/remoteDesktop')
def remotedesktop_sock(ws):
	remotedesktop_before_request()
	while ws.connected and RemoteDesktop._enabled:
		try: c,d=json.loads(ws.receive(10))
		except TypeError: continue
		if not RemoteDesktop._enabled: continue
		if c<=1: RemoteDesktop.keyboard_press(c==0,d)
		elif c<=3: d['p'] = c==2; RemoteDesktop.mouse_press(**d)
		else: RemoteDesktop.mouse_move(**d)

class Lobby:
	lobbies = {}
	lobbyId = 0
	def __init__(s,g,l):
		s.id = Lobby.lobbyId
		Lobby.lobbyId += 1
		Lobby.lobbies[s.id] = s
		s.game = g
		# s.chat = Chat()
		s.location = l
		s.host = "Server"
		s.official = True
		s.name = f"Lobby {s.id}"
		s.ruleset = "ask me"
		s.users = set()
		s.time = 32
		threading.Thread(target=s.lobbyCountdown, daemon=True).start()

	@classmethod
	def getLobbies(c):
		return {lobbyID:c.getLobby(lobby) for lobbyID,lobby in c .lobbies.items() if lobby.game.state == 0}
	@classmethod
	def getLobby(c, lobby):
		return {'name':lobby.name,'official':lobby.official,'host':lobby.host,'time':lobby.time,'game':lobby.location,'ruleset':lobby.ruleset,'players':len(lobby.users)}
	# LEGACY REQUIREMENT
	@classmethod
	def getJoined(c, user, attempted): return {id:(user in Lobby.lobbies[id].users) for id in attempted}
	def join(s, user):
		if s.game.state != 0: return False
		setattr(user, s.location, s.id)
		s.time += 8
		s.lobbyTimeMax()
		s.users.add(user)
		return True
	def lobbyTimeMax(s):
		if len(s.users) <= 1: s.time = 32
		elif len(s.users) >= 3 and s.time > 16: s.time = 16
		else: return False
		return True
	def lobbyCountdown(s):
		while s.time > 0 or len(s.users) <= 1:
			if not s.lobbyTimeMax(): s.time -= 1
			time.sleep(1)
		s.game.start()
	def leave(s, user):
		if s.game.state != 0: return False
		try: s.users.remove(user)
		except KeyError: pass
		s.time += 8
		s.lobbyTimeMax()
		return True

def lobby_before_request(a):
	user = User.usersByHash[flask.session['User']]
	if getattr(user, a) not in Lobby.lobbies:
		setattr(user, a, None)
		flask.abort(400)
@flaskServer.route('/lobbies')
def lobby_home(): return flask.send_file(f'{directory}/lobbies.html')
@flaskSocket.route('/lobbies')
def lobby_sock(ws):
	attempted = set()
	user = User.usersByHash[flask.session['User']]
	while ws.connected:
		ws.send(json.dumps({'data':Lobby.getLobbies(),'joined':Lobby.getJoined(user,attempted)}))
		try: lobbyID = json.loads(ws.receive(10))
		except TypeError: continue
		if user in Lobby.lobbies[lobbyID].users:
			ws.send(json.dumps({0:Lobby.lobbies[lobbyID].location}))
			continue
		attempted.add(lobbyID)
		if lobbyID not in Lobby.lobbies: continue
		elif (Lobby.lobbies[lobbyID].join(user)): ws.send(json.dumps({'joined':{lobbyID:True},0:Lobby.lobbies[lobbyID].location}))

class UnoCard:
	def __init__(s,n,p):
		s.name = n
		for k,v in p.items(): setattr(s,k,v)

@dataclasses.dataclass
class UnoPlayer:
	game: object
	hand: list[str]
	turn: int
	user: User

class Uno:
	basedeck = []
	cards = {}
	lobbies = set()
	with open(f'{directory}/uno/uno.txt') as f: _gamerules = json.loads(f.read())
	for card in _gamerules['Uno']:
		cards[card[0]] = UnoCard(card[0],card[3])
		# for _ in range(card[2]): basedeck.append(card[0])
		for _ in range(card[2]): basedeck.append(cards[card[0]])
	
	_enabled = False
	controlButton = tkinter.Button(buttonTab,text='Uno',command=lambda:Uno.toggle())
	controlButton.configure(background='green',activebackground='yellow',height=5,width=20)
	controlButton.pack(anchor='nw',side=tkinter.LEFT)

	@classmethod
	def toggle(c):
		if c._enabled:
			for id in Uno.lobbies: del Lobby.lobbies[id]
		Uno.lobbies = set()
		c._enabled = not c._enabled
		c.controlButton.configure(background='green' if c._enabled else 'red')
		if c._enabled:
			for _ in range(3): Uno()

	def __init__(s):
		s.drawpile = Uno.basedeck.copy()
		random.shuffle(s.drawpile)
		s.state = 0
		s.lobby = Lobby(s, "uno")
		Uno.lobbies.add(s.lobby.id)
		s.clock = 0
		s.turn = 0
		s.turnDirection = 1
		s.playersByHash = {}
		s.players = []

	def start(s):
		s.state = 1
		for i, user in enumerate(s.lobby.users):
			_ = UnoPlayer(s, [s.drawpile.pop(0) for _ in range(7)], i, user)
			s.players.append(_)
			s.playersByHash[user.userHash] = _
		s.discard = s.drawpile.pop(0) # NEED TO ADD SPECIAL RULES FOR SPECIAL CARDS
		s.discardActionActive = False
		s.discardDraw = 0
		if hasattr(s.discard, "action"):
			match s.discard.action:
				case "Skip": s.turnChange(1)
				case "Reverse": s.turnChange(*((2,-1) if len(s.players)!=2 else (1,1)))
				case "Draw":
					s.discardActionActive = True
					s.discardDraw += 2
		s.state = 2
	def endcheck(s):
		if s.state != 2: return
		for p in s.players:
			if len(p.hand) == 0: s.end()
	def end(s):
		s.state = 3
		for player in s.players: player.user.uno = None
		Uno()
		Lobby.lobbies.remove(s.lobby.id)
		Uno.lobbies.remove(s.lobby.id)

	def turnChange(s,n=1,d=1):
		s.turnDirection *= d
		s.turn += n*s.turnDirection
		while s.turn<0: s.turn += len(s.players)
		while s.turn>=len(s.players): s.turn -= len(s.players)
		s.clock += 1
	def canPlay(s, player, card):
		return True
	def playCard(s, player, card):
		try: card = Uno.cards[card]
		except: return False
		if not s.canPlay(player, card): return False
		s.drawpile.append(s.discard)
		s.discard = card
		player.hand.remove(card)
		if hasattr(card, "action"):
			match card.action:
				case "Skip": s.turnChange(2)
				case "Reverse": s.turnChange(*((1,-1) if len(s.players)!=2 else (2,1)))
				case "Draw":
					s.discardActionActive = True
					s.discardDraw += 2
					s.turnChange()
		else: s.turnChange()
		s.endcheck()
		return True
	def drawCard(s, player):
		if len(s.drawpile) == 0: return (False,)
		drawT = 1 if not s.discardActionActive else s.discardDraw
		s.discardActionActive = False
		s.discardDraw = 0
		drawC = [s.drawpile.pop(0) for _ in range(drawT) if len(s.drawpile) != 0]
		player.hand.extend(drawC)
		s.turnChange()
		return (True, [c.name for c in drawC])
	def getOpponentCount(s,player): return [len(p.hand) for p in s.players if p != player]

def uno_before_request():
	if not Uno._enabled: flask.abort(503)
	lobby_before_request('uno')
@flaskServer.route('/uno')
@flaskServer.route('/uno/lobby')
def uno_lobby():
	uno_before_request()
	return flask.send_file(f'{directory}/uno/lobby.html')
@flaskSocket.route('/uno/lobby')
def uno_lobby_sock(ws):
	uno_before_request()
	user = User.usersByHash[flask.session['User']]
	lobby = Lobby.lobbies[user.uno]
	while ws.connected:
		if(lobby.game.state != 0): break
		ws.send(json.dumps({"data":Lobby.getLobby(lobby)}))
		time.sleep(4)
	if ws.connected: ws.send(json.dumps({0:True}))
@flaskServer.route('/uno/game')
def uno_game():
	uno_before_request()
	with open(f'{directory}/uno/uno.html') as f: return flask.render_template_string(f.read())
@flaskSocket.route('/uno/game')
def uno_game_sock(ws):
	uno_before_request()
	user = User.usersByHash[flask.session['User']]
	game = Lobby.lobbies[user.uno].game
	player = game.playersByHash[user.userHash]
	clock = -1
	while ws.connected:
		if game.state >= 2: break
		time.sleep(1)
	while ws.connected and game.state == 2:
		if clock != game.clock:
			clock = game.clock
			ws.send(json.dumps({'opponents':game.getOpponentCount(player),'turn':player.turn,'gameTurn':game.turn,'discardActive':game.discardActionActive,'discard':game.discard.name,'hand':[c.name for c in player.hand]}))
		try: command = json.loads(ws.receive(1))
		except TypeError: continue
		if game.turn != player.turn: continue
		if 'play' in command.keys():
			if game.playCard(player,command['play']): ws.send(json.dumps({'play':command['play']}))
		elif 'draw' in command.keys():
			r = game.drawCard(player)
			if r[0]: ws.send(json.dumps({'draw':r[1]}))
	if ws.connected:
		ws.send(json.dumps({'opponents':game.getOpponentCount(player),'turn':player.turn,'gameTurn':game.turn,'discardActive':game.discardActionActive,'discard':game.discard.name,'hand':[c.name for c in player.hand]}))
@flaskServer.route('/uno/gamerules')
def uno_gamerules():
	uno_before_request()
	return flask.send_file(f'{directory}/uno/uno.txt')
@flaskServer.route('/uno/file/<path:path>')
def uno_file(path):
	uno_before_request()
	try:
		return flask.send_file(f'{directory}/uno/file/{path}')
	except BaseException as err: print(err)
	flask.abort(404)

class Chat:
	general = None
	chats = {}
	chatidcount = 0
	
	controlButton = tkinter.Button(buttonTab,text="Chat",command=lambda:Chat.toggle())
	controlButton.configure(background='green',activebackground='yellow',height=5,width=20)
	controlButton.pack(anchor='nw',side=tkinter.LEFT)
	_enabled = False
	
	@classmethod
	def toggle(c):
		if c._enabled:
			for obj in list(c.chats.values()):
				obj.destroyEvidence()
			c.general = None
		c._enabled = not c._enabled
		c.controlButton.configure(background='green' if c._enabled else 'red')
		if c._enabled:
			c.general = Chat()
		
	
	def __init__(s):
		s.websockets = set()
		s.chat = []
		s.chatid = Chat.chatidcount
		Chat.chatidcount += 1
		Chat.chats[s.chatid] = s
	def connect(s,ws):
		s.websockets.add(ws)
		s.getMessages(ws)
	def getMessages(s,ws):
		# READ ALL MESSAGES AND SEND TO WEBSOCKET WS
		ws.send(json.dumps({"h":[(nick,user.nickname,m) for nick,user,m in s.chat]}))
	def sendMessage(s,m,nick,user):
		s.chat.append((nick,user,m))
		closedWebsockets = set()
		for websocket in s.websockets:
			try: websocket.send(json.dumps({"m":(nick,m)}))
			except ConnectionClosed: closedWebsockets.add(websocket)
		for websocket in closedWebsockets: s.disconnect(websocket)
	def disconnect(s,ws):
		try: s.websockets.remove(ws)
		except: pass
		try: ws.close()
		except ConnectionClosed: pass
	def destroyEvidence(s):
		del Chat.chats[s.chatid]
		websockets = list(s.websockets)
		for websocket in websockets:
			s.disconnect(websocket)

def chat_before_request():
	if not Chat._enabled: flask.abort(503)
@flaskServer.route("/chat/general")
def chat_home():
	chat_before_request()
	return flask.send_file(f"{directory}/chat/chat.html")
@flaskSocket.route("/chat/general")
def chat_home_sock(ws):
	chat_before_request()
	Chat.general.connect(ws)
	user = User.usersByHash[flask.session['User']]
	while ws.connected:
		m = ws.receive(2)
		if m is None: continue
		nick = user.nickname
		Chat.general.sendMessage(m,nick,user)
	Chat.general.disconnect(ws)

# @flaskServer.route('/edu/http-status-code/<int:code>')
# def site_http_status_code(code): flask.abort(code)

Chat.toggle()
Uno.toggle()

def site_mainloop(): flaskServer.run('0.0.0.0',80)
threading.Thread(target=site_mainloop,daemon=True).start()
SCPTkWindow.mainloop()
