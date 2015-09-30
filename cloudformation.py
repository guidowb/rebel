#!/usr/bin/env python

import sys
import pivnet
import config
import json

def download_template():
	version = config.get('elastic-runtime', 'release')
	product = pivnet.pivnet_select_product('Elastic Runtime')
	release = pivnet.pivnet_select_release(product, version)
	files = pivnet.pivnet_files(product, release, 'cloudformation')
	if len(files) < 1:
		print "no cloudformation template found for release", version
		sys.exit(1)
	if len(files) > 1:
		print "multiple cloudformation templates found for release", version
		sys.exit(1)
	return json.load(pivnet.pivnet_open(files[0]))

def main(argv):
	template = download_template()
#	print json.dumps(template, indent=4)
	parameters = template["Parameters"]
	for key, value in parameters.iteritems():
		print key, value

if __name__ == '__main__':
	main(sys.argv)
