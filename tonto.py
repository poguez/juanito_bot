import sys
import subprocess
import re
import os
import os.path
import argparse
import itertools
import logging
import urllib.request
import lxml.html
import irc.bot
import irc.client
import random
import sqlite3
import configparser
import time
import collections

DEFAULTS = {
		'server': 'irc.freenode.net',
		'nickname': 'tonto_bot',
		'channel': '#coderspuebla',
		'realname': 'Tontus Hominidus Bot',
		'port': 6667
		}

def get_urls(s):
	return re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', s)

class TontoBot(irc.bot.SingleServerIRCBot):
	FETCH_MAX = 20 * 1024
	URL_MAXLEN = 60 # If url is longer than this, tontobot will provide a tinified version of the url
	MSG_MAX = 140
	FAIL_MSGS = [':(', '):', '?', 'WAT', 'No pos no', 'link no worky', 'chupa limon']
	URL_TABLE = '''urls (
					url			TEXT PRIMARY KEY	NOT NULL,
					title		TEXT				NOT NULL,
					user		TEXT				NOT NULL,
					time		TEXT				NOT NULL);'''

	def __init__(self, serverspec, channel, nickname, realname, dbpath='./seenurls.db'):
		irc.bot.SingleServerIRCBot.__init__(self, [serverspec], nickname, realname)
		self.channel = channel
		logging.info("nickname=[%s] realname=[%s] channel=[%s]" % (nickname, realname, channel))
		try:
			self.sqlcon = sqlite3.connect(dbpath)
			self.sqlcon.row_factory = sqlite3.Row
			self.sqlcur = self.sqlcon.cursor()
			self.sqlcon.execute('CREATE TABLE IF NOT EXISTS ' + self.URL_TABLE)
		except:
			logging.exception("Unable to open URL database!")
			raise

	def on_welcome(self, connection, event):
		logging.debug("joining %s", self.channel)
		connection.join(self.channel)

	def _sendmsg(self, connection, msg):
		"""Convenience method to send a msg. Truncates msg to MSG_MAX chars"""
		msg = msg.replace('\n', ' ')
		logging.info("msg: %s" % msg)
		if len(msg) > 140:
			msg = msg[:self.MSG_MAX]
			logging.info("truncated msg: %s" % msg)
		connection.privmsg(self.channel, msg)

	def urlopen(self, url, maxbytes=FETCH_MAX):
		req = urllib.request.Request(url, headers={'User-agent': 'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11'})
		fd = urllib.request.urlopen(req)
		return fd.read(maxbytes)

	def tinify(self, url):
		return self.urlopen('http://tinyurl.com/api-create.php?url=%s' % url).decode('utf-8')


	def rtfm(self, line):
		argv = line.split()
		if len(argv) == 3:
			cmd = argv[2].strip()
			section = argv[1]
		elif len(argv) == 2:
			cmd = argv[1].strip()
			section = None
		else:
			raise Exception("format: !rtfm [section] cmd")

		if not re.match('^[a-zA-Z_-]+$', cmd):
			logging.error("re.match rtfm: %s" % cmd)
			raise Exception("Funky commands not supported")

		if section:
			stdout = subprocess.check_output(['man', '--pager', 'cat', str(section), cmd])
		else:
			stdout = subprocess.check_output(['man', '--pager', 'cat', cmd])
		stdout = stdout.decode('utf-8')

		if stdout:
			seen_description = False
			for line in stdout.splitlines():
				line = line.strip()
				if seen_description:
					return line.split('.')[0]
				if line.endswith('DESCRIPTION'):
					seen_description = True
			raise Exception("Unable to parse manpage")

		raise Exception("No man page found")

	def on_pubmsg(self, connection, event):
		line = event.arguments[0]
		user = event.source.split('!')[0]
		try:
			if line.startswith('!rtfm'):
				self._sendmsg(connection, self.rtfm(line))
			elif line.startswith('ping'):
				self._sendmsg(connection, 'pong')
			elif line.startswith('!juanito'):
				self._sendmsg(connection, 'Hola terricolas.')
		except:
			logging.exception("Failed with: %s" % line)
		for url in get_urls(line):
			msg = collections.deque()
			try:
				if url.endswith(('.jpg', '.png', '.git', '.bmp', '.pdf')):
					logging.info('not a webpage, skipping')
					continue
				root = lxml.html.fromstring(self.urlopen(url))
				title = root.find('.//title').text
				self.sqlcur.execute('SELECT user FROM urls WHERE url = ?', (url,))
				sqlrow = self.sqlcur.fetchone()
				if sqlrow is not None:
					msg.append('[repost: %s]' % sqlrow['user'])
				else:
					self.sqlcur.execute('INSERT INTO urls VALUES (?,?,?,?)', (url, title, user, time.time(),))
					self.sqlcon.commit()
				if len(url) > self.URL_MAXLEN:
					msg.append('[%s]' % self.tinify(url))
				msg.append(title)
				self._sendmsg(connection, ' '.join(msg))
			except:
				logging.exception("Failed with: %s" % line)
				self._sendmsg(connection, random.choice(self.FAIL_MSGS))

def get_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('--server')
	parser.add_argument('--nickname')
	parser.add_argument('--channel')
	parser.add_argument('--realname')
	parser.add_argument('-p', '--port', type=int)
	return parser.parse_args()


def main():
	logging.basicConfig(level=logging.INFO)
	config = configparser.ConfigParser()
	config.read(['./tontorc', os.path.expanduser('~/.tontorc')])
	args = get_args()

	server = args.server or config['net'].get('server', DEFAULTS['server'])
	nickname = args.nickname or config['net'].get('nickname', DEFAULTS['nickname'])
	channel = args.channel or config['net'].get('channel', DEFAULTS['channel'])
	realname = args.realname or config['net'].get('realname', DEFAULTS['realname'])
	port = args.port or config['net'].getint('port', DEFAULTS['port'])

	# Do not try to decode lines
	irc.buffer.DecodingLineBuffer.errors = 'replace'
	serverspec = irc.bot.ServerSpec(server, port)
	bot = TontoBot(serverspec, channel, nickname, realname)
	try:
		c = bot.start()
	except irc.client.ServerConnectionError:
		logging.error((sys.exc_info()[1]))
		sys.exit(1)

if __name__ == '__main__':
	main()
