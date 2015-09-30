#!/usr/bin/env python

import sys
import ConfigParser

CONFIG_FILE = "ramble.cfg"
CONFIG = None
UNSPECIFIED = {}

def get(section, key, default=UNSPECIFIED):
	global CONFIG
	if CONFIG is None:
		CONFIG = load_config()
	try:
		return CONFIG.get(section, key)
	except ConfigParser.NoSectionError:
		if default is UNSPECIFIED:
			print "Config file", CONFIG_FILE, "must have section named", section
			sys.exit(1)
	except ConfigParser.NoOptionError:
		if default is UNSPECIFIED:
			print "Config file", CONFIG_FILE, "section", section, "must specify value for", key
			sys.exit(1)
	except ConfigParser.Error as error:
		print error
		sys.exit(1)
	return None

def load_config():
	config = ConfigParser.SafeConfigParser()
	config.read(CONFIG_FILE)
	return config

def main(argv):

	""" Pre-configure ramble with all required values so that it can run unattended later """

if __name__ == "__main__":
	main(sys.argv)