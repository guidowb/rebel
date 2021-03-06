#!/usr/bin/env python

import sys
import config
import urllib, urllib2
import json
import os.path
import errno
import cli

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
	all_products = json.load(pivnet_get(url))
	products = [p for p in all_products["products"] if product_pattern == p["name"]]
	if len(products) == 0:
		products = [p for p in all_products["products"] if product_pattern in p["name"]]
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
	all_releases = json.load(pivnet_get(url))
	releases = [r for r in all_releases["releases"] if release_pattern == r["version"]]
	if len(releases) == 0:
		releases = [r for r in all_releases["releases"] if release_pattern in r["version"]]
	return releases

def pivnet_select_release(product, release_pattern=None):
	if release_pattern is None:
		return pivnet_latest_release(product)
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

def pivnet_latest_release(product, controlled=False):
	releases = pivnet_releases(product)
	if not controlled:
		releases = [r for r in releases if not r["controlled"] == 'true']
	if len(releases) < 1:
		print "No matching releases available for product"
		sys.exit(1)
	return sorted(releases, key=lambda release: release["release_date"])[-1]

def pivnet_files(product, release, file_pattern = ""):
	url = 'https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases/' + str(release["id"]) + '/product_files'
	all_files = json.load(pivnet_get(url))
	files = [f for f in all_files["product_files"] if file_pattern == os.path.basename(f["aws_object_key"])]
	if len(files) == 0:
		files = [f for f in all_files["product_files"] if file_pattern in os.path.basename(f["aws_object_key"])]
	return files

def pivnet_accept_eula(product, release):
	url = 'https://network.pivotal.io/api/v2/products/' + str(product["id"]) + '/releases/' + str(release["id"]) + '/eula_acceptance'
	acceptance = json.load(pivnet_post(url, {}))

def pivnet_open(file):
	PIVNET_TOKEN = config.get('pivotal-network', 'token')
	url = file["_links"]["download"]["href"]
	request = urllib2.Request(url)
	request.add_header('Authorization', 'Token ' + PIVNET_TOKEN)
	try:
		return urllib2.urlopen(request, data=urllib.urlencode({}))
	except urllib2.HTTPError as error:
		if error.code == 451:
			print "You must accept-eula before downloading files"
		else:
			print error.reason, '(', error.code, ')'
		sys.exit(1)

def pivnet_download(product, release, files, progress=False):
	target_dir = product["slug"]
	mkdir_p(target_dir)
	downloads = []
	for f in files:
		blocksize = 1 * 1024 * 1024
		target_name = target_dir + "/" + os.path.basename(f["aws_object_key"])
		source = pivnet_open(f)
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
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	product_pattern = argv[1]
	release_pattern = argv[2] if len(argv) > 2 else ""
	product = pivnet_select_product(product_pattern)
	releases = pivnet_releases(product, release_pattern)
	print "\n".join([r["version"] for r in releases])

def list_files(argv):
	cli.exit_with_usage(argv) if len(argv) < 3 else None
	product_pattern = argv[1]
	release_pattern = argv[2]
	file_pattern = argv[3] if len(argv) > 3 else ""
	product = pivnet_select_product(product_pattern)
	release = pivnet_select_release(product, release_pattern)
	files = pivnet_files(product, release, file_pattern)
	print "\n".join([product["slug"] + "/" + os.path.basename(f["aws_object_key"]) for f in files])

def accept_eula(argv):
	cli.exit_with_usage(argv) if len(argv) < 3 else None
	product_pattern = argv[1]
	release_pattern = argv[2]
	product = pivnet_select_product(product_pattern)
	release = pivnet_select_release(product, release_pattern)
	pivnet_accept_eula(product, release)

def download(argv):
	cli.exit_with_usage(argv) if len(argv) < 3 else None
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

commands = {
	"products":    { "func": list_products, "usage": "products [<product-name>]" },
	"releases":    { "func": list_releases, "usage": "releases <product-name> [<release-name>]" },
	"accept-eula": { "func": accept_eula,   "usage": "accept-eula <product-name> <release-name>" },
	"files":       { "func": list_files,    "usage": "files <product-name> <release-name> [<file-name>]" },
	"download":    { "func": download,      "usage": "download <product-name> <release-name> [<file-name>]" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)