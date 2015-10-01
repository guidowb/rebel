#!/usr/bin/env python

import aws
import cli
import sys
import json

def opsmgr_list_images():
	command = [
		'ec2',
		'describe-images',
		'--filters', 'Name=name,Values=pivotal-ops-manager-v*'
	]
	return json.loads(aws.aws_cli_verbose(command))["Images"]

def list_images_cmd(argv):
	images = opsmgr_list_images()
	print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])

commands = {
	"images":       { "func": list_images_cmd,    "usage": "images" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)