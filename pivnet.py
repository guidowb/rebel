#!/usr/bin/env python

import sys
import config
import urllib, urllib2
import json
import os.path
import errno

""" Pivotal Network API """

def pivnet_request(url):
	PIVNET_TOKEN = config.get('pivotal-network', 'token')
	request = urllib2.Request(url)
	request.add_header('Authorization', 'Token ' + PIVNET_TOKEN)
	request.add_header('Content-type', 'application/json')
	request.add_header('Accept', 'application/json')
	return request

def pivnet_get(url):
	return urllib2.urlopen(pivnet_request(url))

def pivnet_post(url, data):
	return urllib2.urlopen(pivnet_request(url), data=urllib.urlencode(data))

def pivnet_products(product_pattern = ""):
	url = 'https://network.pivotal.io/api/v2/products'
	products = json.load(pivnet_get(url))
	products = [p for p in products["products"] if product_pattern in p["name"]]
	return products

def pivnet_select_product(product_pattern):
	products = pivnet_products(product_pattern)
	if len(products) < 1:
		print product_pattern, "does not match any products. Available products are:"
		print "\n".join(["   " + p["name"] for p in pivnet_products()])
		sys.exit(1)
	if len(products) > 1:
		print product_pattern, "matches multiple products:"
		print "\n".join(["   " + p["name"] for p in products])
		print "Please be more specific"
		sys.exit(1)
	return products[0]

def pivnet_releases(product, release_pattern = ""):
	url = 'https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases'
	releases = json.load(pivnet_get(url))
	releases = [r for r in releases["releases"] if release_pattern in r["version"]]
	return releases

def pivnet_select_release(product, release_pattern):
	releases = pivnet_releases(product, release_pattern)
	if len(releases) < 1:
		print release_pattern, "does not match any releases. Available releases are:"
		print "\n".join(["   " + r["version"] for r in pivnet_releases(product)])
		sys.exit(1)
	if len(releases) > 1:
		print release_pattern, "matches multiple releases:"
		print "\n".join(["   " + r["version"] for r in releases])
		print "Please be more specific"
		sys.exit(1)
	return releases[0]

def pivnet_files(product, release, file_pattern = ""):
	url = 'https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases/' + str(release["id"]) + '/product_files'
	files = json.load(pivnet_get(url))
	files = [f for f in files["product_files"] if file_pattern in os.path.basename(f["aws_object_key"])]
	return files

def pivnet_accept_eula(product, release):
	url = 'https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases/' + str(release["id"]) + '/eula_acceptance'
	acceptance = json.load(pivnet_post(url, {}))

def pivnet_download(product, release, files, progress=False):
	PIVNET_TOKEN = config.get('pivotal-network', 'token')
	target_dir = product["slug"]
	mkdir_p(target_dir)
	downloads = []
	for f in files:
		blocksize = 1 * 1024 * 1024
		source_url = f["_links"]["download"]["href"]
		target_name = target_dir + "/" + os.path.basename(f["aws_object_key"])
		request = urllib2.Request(source_url)
		request.add_header('Authorization', 'Token ' + PIVNET_TOKEN)
		source = urllib2.urlopen(request, data=urllib.urlencode({}))
		if progress:
			sys.stdout.write(target_name + ' ')
			sys.stdout.flush()
		with open(target_name, 'w+') as target:
			data = source.read(blocksize)
			while len(data) > 0:
				target.write(data)
				if progress:
					sys.stdout.write('.')
					sys.stdout.flush()
				data = source.read(blocksize)
		if progress:
			sys.stdout.write('\n')
		downloads.append(target_name)
	return downloads

def mkdir_p(dir):
	try:
		os.makedirs(dir)
	except os.error, e:
		if e.errno != errno.EEXIST:
			raise

""" Pivotal Network CLI exercising Pivotal Network API """

def list_products(argv):
	product_pattern = argv[1] if len(argv) > 1 else ""
	products = pivnet_products(product_pattern)
	print "\n".join([p["name"] for p in products])

def list_releases(argv):
	exit_with_usage(argv) if len(argv) < 2 else None
	product_pattern = argv[1]
	release_pattern = argv[2] if len(argv) > 2 else ""
	product = pivnet_select_product(product_pattern)
	releases = pivnet_releases(product, release_pattern)
	print "\n".join([r["version"] for r in releases])

def list_files(argv):
	exit_with_usage(argv) if len(argv) < 3 else None
	product_pattern = argv[1]
	release_pattern = argv[2]
	file_pattern = argv[3] if len(argv) > 3 else ""
	product = pivnet_select_product(product_pattern)
	release = pivnet_select_release(product, release_pattern)
	files = pivnet_files(product, release, file_pattern)
	print "\n".join([product["slug"] + "/" + os.path.basename(f["aws_object_key"]) for f in files])

def accept_eula(argv):
	exit_with_usage(argv) if len(argv) < 3 else None
	product_pattern = argv[1]
	release_pattern = argv[2]
	product = pivnet_select_product(product_pattern)
	release = pivnet_select_release(product, release_pattern)
	pivnet_accept_eula(product, release)

def download(argv):
	exit_with_usage(argv) if len(argv) < 3 else None
	product_pattern = argv[1]
	release_pattern = argv[2]
	file_pattern = argv[3] if len(argv) > 3 else ""
	product = pivnet_select_product(product_pattern)
	release = pivnet_select_release(product, release_pattern)
	files = pivnet_files(product, release, file_pattern)
	try:
		pivnet_download(product, release, files, True)
	except urllib2.HTTPError as error:
		if error.code == 451:
			print "You must accept-eula before downloading files"
		else:
			print error.reason, '(', error.code, ')'
		sys.exit(1)

""" Pretty much generic CLI module """

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
	"help":        { "func": print_help,    "usage": "help" },
	"products":    { "func": list_products, "usage": "products [<product-name>]" },
	"releases":    { "func": list_releases, "usage": "releases <product-name> [<release-name>]" },
	"accept-eula": { "func": accept_eula,   "usage": "accept-eula <product-name> <release-name>" },
	"files":       { "func": list_files,    "usage": "files <product-name> <release-name> [<file-name>]" },
	"download":    { "func": download,      "usage": "download <product-name> <release-name> [<file-name>]" },
}

def main(argv):
	exit_with_usage() if len(argv) < 2 else None
	command = commands.get(argv[1], { "func": unknown_command } )
	result = command["func"](argv[1:])
	sys.exit(result)

if __name__ == '__main__':
	main(sys.argv)