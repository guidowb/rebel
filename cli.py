#!/usr/bin/env python

""" Generic CLI module """

import sys

commands = {}

def unknown_command(argv):
	print "unknown command", argv[0]
	return 1

def print_help(argv = None):
	for name, command in commands.iteritems():
		print command["usage"]

def print_usage(argv):
	print "Usage:", commands.get(argv[0])["usage"]

def exit_with_usage(argv = None):
	if argv is None:
		print_help()
	else:
		print_usage(argv)
	sys.exit(1)

def cli(argv, client_commands):
	global commands
	commands = client_commands
	commands["help"] = { "func": print_help, "usage": "help" }
	exit_with_usage() if len(argv) < 2 else None
	command = commands.get(argv[1], { "func": unknown_command } )
	result = command["func"](argv[1:])
	sys.exit(result)