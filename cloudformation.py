#!/usr/bin/env python

import sys
import pivnet
import config
import json
import aws

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

def friendly_name(oldname):
	""" Completely unnecessary but the template parameter names offend my sensibilities """
	newname = ""
	oldname = oldname.lstrip('0123456789') + "-"
	hasdash = True
	for i in range(len(oldname) - 1):
		c1 = oldname[i]
		c2 = oldname[i+1]
		if c1.isupper() and c2.islower() and not hasdash:
			newname += '-' + c1.lower()
		elif c1.islower() and c2.isupper():
			newname += c1 + '-'
			hasdash = True
		else:
			newname += c1.lower()
			hasdash = False
	return newname

def required_parameters(template):
	parameters = []
	for key in template["Parameters"]:
		value = None
		if template["Parameters"][key].get("Default", None) is not None:
			value = config.get('aws', friendly_name(key), None)
		else:
			value = config.get('aws', friendly_name(key))
		if value is not None:
			parameters.append({
				"ParameterKey": key,
				"ParameterValue": config.get('aws', friendly_name(key)),
				"UsePreviousValue": False
				})
	return json.dumps(parameters)

def create_stack(template):
	command = [
		'cloudformation',
		'create-stack',
		'--stack-name', 'unique',
		'--template-body', json.dumps(template),
		'--on-failure', 'DO_NOTHING',
		'--parameters', required_parameters(template),
		'--capabilities', 'CAPABILITY_IAM'
	]
	aws.aws_cli_verbose(command)

def main(argv):
	template = download_template()
	create_stack(template)

if __name__ == '__main__':
	main(sys.argv)
