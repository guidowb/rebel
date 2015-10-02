#!/usr/bin/env python

import aws
import cli
import sys
import json

def opsmgr_list_images(region = None):
	command = [
		'ec2',
		'describe-images',
		'--filters', 'Name=name,Values=pivotal-ops-manager-v*'
	]
	if region is not None:
		command.extend(['--region', region])
	return json.loads(aws.aws_cli_verbose(command))["Images"]

def list_images_cmd(argv):
	region = argv[1] if len(argv) > 1 else None
	images = opsmgr_list_images(region)
	images = sorted(images, key=lambda image: image["CreationDate"])
	images.reverse()
	print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])

commands = {
	"images":       { "func": list_images_cmd,    "usage": "images [<region>]" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)