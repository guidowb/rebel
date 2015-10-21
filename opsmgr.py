#!/usr/bin/env python

import aws
import cli
import sys
import json
import urllib, urllib2
import cloudformation
import config
import ssl
import time
import random
import string

""" OpsManager API """

def opsmgr_list_images(region = None):
	command = [
		'ec2',
		'describe-images',
		'--filters', 'Name=name,Values=pivotal-ops-manager-v*'
	]
	if region is not None:
		command.extend(['--region', region])
	images = json.loads(aws.aws_cli_verbose(command))["Images"]
	images = sorted(images, key=lambda image: image["CreationDate"])
	images.reverse()
	return images

def opsmgr_select_image(version, verbose=False):
	images = opsmgr_list_images()
	image = next((i for i in images if i["Name"].startswith("pivotal-ops-manager-v" + version)), None)
	if verbose and image is None:
		print "No ops-manager image found for version", version
		if len(images) > 0:
			print "Available images are:"
			print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])
		sys.exit(1)
	return image

def opsmgr_launch_instance(stack, version=None, verbose=False):
	version = cloudformation.get_tag(stack, "pcf-version") if version is None else version
	image = opsmgr_select_image(version, verbose)
	if verbose:
		print "Launching OpsMgr instance from", image["ImageId"] + ":", image["Description"]
	command = [
		'ec2',
		'run-instances',
		'--image-id', image["ImageId"],
		'--instance-type', 'm3.large',
		'--subnet-id', cloudformation.get_output(stack, "PcfPublicSubnetId"),
		'--associate-public-ip-address',
		'--block-device-mapping', 'DeviceName=/dev/sda1,Ebs={VolumeSize=100}',
		'--security-group-ids', cloudformation.get_output(stack, "PcfOpsManagerSecurityGroupId"),
		'--key-name', config.get('aws', 'nat-key-pair')
	]
	instance = json.loads(aws.aws_cli_verbose(command))["Instances"][0]
	tags = [
		{ "Key": "Name", "Value": "Ops Manager" },
		{ "Key": "Stack", "Value": stack["StackName"] },
		{ "Key": "Image", "Value": image["Description"] }
	]
	command = [
		'ec2',
		'create-tags',
		'--resources', instance["InstanceId"],
		'--tags', json.dumps(tags)
	]
	aws.aws_cli_verbose(command)
	return instance

def opsmgr_terminate_instances(stack):
	instances = opsmgr_find_instances(stack)
	if len(instances) < 1:
		return
	instance_ids = [ i["InstanceId"] for i in instances]
	command = [
		'ec2',
		'terminate-instances',
		'--instance-ids'
	]
	aws.aws_cli_verbose(command + instance_ids)

def opsmgr_find_instances(stack=None):
	filters = [
		{ "Name": "tag:Name", "Values": [ "Ops Manager" ] },
		{ "Name": "tag-key",  "Values": [ "Stack" ] },
		{ "Name": "instance-state-name", "Values": [ "pending", "running"] }
	]
	if stack is not None:
		filters.extend([ { "Name": "subnet-id", "Values": [ cloudformation.get_output(stack, "PcfPublicSubnetId") ] } ])
	command = [
		'ec2',
		'describe-instances',
		'--filters', json.dumps(filters)
	]
	reservations = json.loads(aws.aws_cli_verbose(command))["Reservations"]
	instances = []
	for r in reservations:
		instances += r["Instances"]
	return instances

def opsmgr_get_tag(instance, key):
	tags = instance["Tags"]
	tag = next((t for t in tags if t["Key"] == key), None)
	return tag["Value"] if tag is not None else None

def opsmgr_url(stack):
	instances = opsmgr_find_instances(stack)
	if len(instances) < 1:
		print stack["StackName"], "does not have an Ops Manager instance"
		sys.exit(1)
	return "https://" + instances[0]["PublicDnsName"]

def opsmgr_request(stack, url):
	url = opsmgr_url(stack) + url
	request = urllib2.Request(url)
	request.add_header('Accept', 'application/json')
	return request	

def opsmgr_get(stack, url):
	context = ssl._create_unverified_context()
	request = opsmgr_request(stack, url)
	request.add_header('Content-type', 'application/json')
	return urllib2.urlopen(opsmgr_request(stack, url), context=context)

def opsmgr_post(stack, url, data):
	context = ssl._create_unverified_context()
	return urllib2.urlopen(opsmgr_request(stack, url), data=urllib.urlencode(data), context=context)

def opsmgr_wait(stack):
	while True:
		try:
			opsmgr_get(stack, "/api/api_version")
			break
		except urllib2.HTTPError as error:
			if error.code == 502:
				pass
			else:
				break
		except:
			pass
		time.sleep(5)

def opsmgr_setup_admin(stack):
	opsmgr_wait(stack)
	username = "admin"
	password = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(16))
	setup = {
		"setup[user_name]": username,
		"setup[password]": password,
		"setup[password_confirmation]": password,
		"setup[eula_accepted]": "true"
	}
	try:
		result = json.load(opsmgr_post(stack, "/api/setup", setup))
		print "Set up new admin user"
		print "Username:", username
		print "Password:", password
	except urllib2.HTTPError as error:
		if error.code == 422:
			print "Admin user is already set up, password remains unchanged"

""" OpsManager CLI exercising OpsManager API """

def list_images_cmd(argv):
	region = argv[1] if len(argv) > 1 else None
	images = opsmgr_list_images(region)
	print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])

def launch_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	version = argv[2] if len(argv) > 2 else ""
	stack = cloudformation.select_stack(stack_name)
	instance = opsmgr_launch_instance(stack, version, verbose=True)
	print "Launched instance", instance["InstanceId"]

def terminate_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	if stack is None:
		print "Stack", stack_name, "not found"
		sys.exit(1)
	opsmgr_terminate_instances(stack)

def list_instances_cmd(argv):
	instances = opsmgr_find_instances()
	for i in instances:
		state = "(pending)" if i["State"]["Name"] == "pending" else ""
		print opsmgr_get_tag(i, "Stack"), "(" + opsmgr_get_tag(i, "Image") + ")", i["PublicDnsName"]

def setup_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	if stack is None:
		print "Stack", stack_name, "not found"
		sys.exit(1)
	opsmgr_setup_admin(stack)

commands = {
	"images":    { "func": list_images_cmd,    "usage": "images [<region>]" },
	"launch":    { "func": launch_cmd,         "usage": "launch <stack-name> <version>" },
	"instances": { "func": list_instances_cmd, "usage": "instances" },
	"terminate": { "func": terminate_cmd,      "usage": "terminate <stack-name>" },
	"setup":     { "func": setup_cmd,          "usage": "setup <stack-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)