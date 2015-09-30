#!/usr/bin/env python

import sys
import config
import urllib2
import json
import pprint

PP = pprint.PrettyPrinter(indent=4)

def pivnet_open(url):
	PIVNET_TOKEN = config.get('pivotal-network', 'token')
	request = urllib2.Request(url)
	request.add_header('Authorization', 'Token ' + PIVNET_TOKEN)
	request.add_header('Content-type', 'application/json')
	request.add_header('Accept', 'application/json')
	return urllib2.urlopen(request)

def pivnet_products(pattern = ""):
	products = json.load(pivnet_open('https://network.pivotal.io/api/v2/products'))
	products = [p for p in products["products"] if pattern in p["name"]]
	return products

def list_products(argv):
	pattern = argv[1] if len(argv) > 1 else ""
	products = pivnet_products(pattern)
	print "\n".join([p["name"] for p in products])

def unknown_command(argv):
	print "unknown command", argv[0]
	return 1

def print_help(argv = None):
	for name, command in commands.iteritems():
		print command["usage"]

def check_argv(argv):
	if len(argv) < 2:
		print_help()
		sys.exit(1)

commands = {
	"help":     { "func": print_help,    "usage": "help" },
	"products": { "func": list_products, "usage": "products [<pattern>]" },
}

def main(argv):
	check_argv(argv)
	command = commands.get(argv[1], { "func": unknown_command } )
	result = command["func"](argv[1:])
	sys.exit(result)

if __name__ == '__main__':
	main(sys.argv)