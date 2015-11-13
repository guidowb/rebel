#!/usr/bin/env python

import os
import sys
import ConfigParser

CONFIG_FILE = os.path.expanduser("~/.rebel.cfg")
CONFIG = None
UNSPECIFIED = {}

def get(section, key, default=UNSPECIFIED, stack=None):
	if stack is not None:
		value = get('stack-' + stack, key, default=None)
		if value is not None:
			return value
	global CONFIG
	if CONFIG is None:
		CONFIG = load_config()
	try:
		value = CONFIG.get(section, key)
		if stack is not None:
			set(section, key, value, stack)
		return value
	except ConfigParser.NoSectionError:
		if default is UNSPECIFIED:
			print "Config file", CONFIG_FILE, "must have a global section named", section
			if stack is not None:
				print "or a stack-specific section named", 'stack-' + stack
			sys.exit(1)
	except ConfigParser.NoOptionError:
		if default is UNSPECIFIED:
			print "Config file must specify value for", key, "in section", section
			if stack is not None:
				print "if it is not in the stack-specific section named", 'stack-' + stack
			sys.exit(1)
	except ConfigParser.Error as error:
		print error
		sys.exit(1)
	return None

def set(section, key, value, stack=None):
	if stack is not None:
		section = 'stack-' + stack
	global CONFIG
	if CONFIG is None:
		CONFIG = load_config()
	try:
		CONFIG.add_section(section)
	except ConfigParser.DuplicateSectionError:
		pass
	CONFIG.set(section, key, value)
	save_config()

def remove(section, key):
	global CONFIG
	if CONFIG is None:
		CONFIG = load_config()
	CONFIG.remove_option(key)
	save_config()

def load_config():
	config = ConfigParser.SafeConfigParser()
	config.read(CONFIG_FILE)
	return config

def save_config():
	global CONFIG
	if CONFIG is not None:
		with open(CONFIG_FILE, 'wb') as config_file:
			CONFIG.write(config_file)

def remove_section(section):
	global CONFIG
	if CONFIG is None:
		CONFIG = load_config()
	CONFIG.remove_section(section)
	save_config()

def main(argv):

	""" Pre-configure rebel with all required values so that it can run unattended later """

if __name__ == "__main__":
	main(sys.argv)
