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

def pivnet_products(product_pattern = ""):
	products = json.load(pivnet_open('https://network.pivotal.io/api/v2/products'))
	products = [p for p in products["products"] if product_pattern in p["name"]]
	return products

def pivnet_select_product(product_pattern):
	products = pivnet_products(product_pattern)
	if len(products) < 1:
		print product_pattern, "does not match any products"
		sys.exit(1)
	if len(products) > 1:
		print product_pattern, "matches multiple products:"
		print "\n".join(["   " + p["name"] for p in products])
		print "Please be more specific"
		sys.exit(1)
	return products[0]

def pivnet_releases(product_pattern, release_pattern = ""):
	product = pivnet_select_product(product_pattern)
	releases = json.load(pivnet_open('https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases'))
	releases = [r for r in releases["releases"] if release_pattern in r["version"]]
	return releases

def list_products(argv):
	product_pattern = argv[1] if len(argv) > 1 else ""
	products = pivnet_products(product_pattern)
	print "\n".join([p["name"] for p in products])

def list_releases(argv):
	exit_with_usage(argv) if len(argv) < 2 else None
	product_pattern = argv[1]
	release_pattern = argv[2] if len(argv) > 2 else ""
	releases = pivnet_releases(product_pattern, release_pattern)
	print "\n".join([r["version"] for r in releases])

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

commands = {
	"help":     { "func": print_help,    "usage": "help" },
	"products": { "func": list_products, "usage": "products [<product-name>]" },
	"releases": { "func": list_releases, "usage": "releases <product-name> [<release-name>]"}
}

def main(argv):
	exit_with_usage() if len(argv) < 2 else None
	command = commands.get(argv[1], { "func": unknown_command } )
	result = command["func"](argv[1:])
	sys.exit(result)

if __name__ == '__main__':
	main(sys.argv)