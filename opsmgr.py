#!/usr/bin/env python

import os
import aws
import cli
import sys
import json
import urllib, urllib2
import httplib
import cloudformation
import config
import ssl
import time
import random
import string
import base64
import yaml
import mimetools
import bosh
import pivnet
import subprocess

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
		print "Launching Ops Manager instance from", image["ImageId"] + ":", image["Description"]
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

def opsmgr_select_instance(stack):
	instances = opsmgr_find_instances(stack)
	if len(instances) < 1:
		print stack["StackName"], "does not have an Ops Manager instance"
		sys.exit(1)
	return instances[0]

def opsmgr_get_tag(instance, key):
	tags = instance["Tags"]
	tag = next((t for t in tags if t["Key"] == key), None)
	return tag["Value"] if tag is not None else None

def opsmgr_hostname(stack):
	instance = opsmgr_select_instance(stack)
	return instance["PublicDnsName"]

def opsmgr_url(stack):
	return "https://" + opsmgr_hostname(stack)

def opsmgr_request(stack, url):
	url = opsmgr_url(stack) + url
	request = urllib2.Request(url)
	request.add_header('Accept', 'application/json')
	username = config.get("stack-" + stack["StackName"], "opsmgr-username", "admin")
	password = config.get("stack-" + stack["StackName"], "opsmgr-password", None)
	if password is not None:
		base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
		request.add_header("Authorization", "Basic %s" % base64string)
	return request	

def opsmgr_get(stack, url):
	context = ssl._create_unverified_context()
	request = opsmgr_request(stack, url)
	request.add_header('Accept', 'application/json')
	return urllib2.urlopen(opsmgr_request(stack, url), context=context)

def opsmgr_delete(stack, url):
	context = ssl._create_unverified_context()
	username = config.get("stack-" + stack["StackName"], "opsmgr-username", "admin")
	password = config.get("stack-" + stack["StackName"], "opsmgr-password", None)
	headers = {}
	if password is not None:
		base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
		headers = {
			"Authorization": "Basic %s" % base64string
		}
	connection = httplib.HTTPSConnection(opsmgr_hostname(stack), context=context)
	connection.request("DELETE", url, headers=headers)
	response = connection.getresponse()
	return response

def opsmgr_post(stack, url, data):
	context = ssl._create_unverified_context()
	return urllib2.urlopen(opsmgr_request(stack, url), data=data, context=context)

def opsmgr_post_yaml(stack, url, name, data):
	context = ssl._create_unverified_context()
	boundary = mimetools.choose_boundary()
	body  = '--' + boundary + '\r\n'
	body += 'Content-Disposition: form-data; name="' + name + '"; filename="somefile.yml"\r\n'
	body += 'Content-Type: text/yaml\r\n'
	body += '\r\n'
	body += yaml.safe_dump(data) + '\r\n'
	body += '--' + boundary + '--\r\n'
	request = opsmgr_request(stack, url)
	request.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)
	return urllib2.urlopen(request, data=body, context=context)

def opsmgr_wait(stack, verbose=False):
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
		if verbose:
			sys.stdout.write('.')
			sys.stdout.flush()
	if verbose:
		print

def opsmgr_setup(stack):
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
		result = json.load(opsmgr_post(stack, "/api/setup", urllib.urlencode(setup)))
		config.set("stack-" + stack["StackName"], "opsmgr-username", username)
		config.set("stack-" + stack["StackName"], "opsmgr-password", password)
	except urllib2.HTTPError as error:
		if error.code == 422:
			return
		print "Error", error.code, error.reason
		sys.exit(1)

def opsmgr_install(stack):
	params = {
		"ignore_warnings": "true"
	}
	install = json.load(opsmgr_post(stack, "/api/installation", urllib.urlencode(params)))
	install_id = str(install["install"]["id"])
	config.set("stack-" + stack["StackName"], "opsmgr-install", install_id)
	return install_id

def opsmgr_uninstall(stack):
	install = json.load(opsmgr_delete(stack, "/api/installation"))
	install_id = str(install["install"]["id"])
	config.set("stack-" + stack["StackName"], "opsmgr-install", install_id)
	return install_id

def opsmgr_logs(stack, install_id=None):
	if install_id is None:
		install_id = config.get("stack-" + stack["StackName"], "opsmgr-install", None)
	if install_id is None:
		print "No installation in progress"
		return []
	log = opsmgr_get(stack, "/api/installation/" + str(install_id) + "/logs")
	return json.load(log)["logs"].splitlines()

def opsmgr_tail_logs(stack, install_id=None):
	if install_id is None:
		install_id = config.get("stack-" + stack["StackName"], "opsmgr-install", None)
	if install_id is None:
		print "No installation in progress"
		return
	lines_shown = 0
	in_event = False
	while True:
		log_lines = opsmgr_logs(stack, install_id)
		for line in log_lines[lines_shown:]:
			if line.startswith('{'):
				event = json.loads(line)
				event_type = event.get("type", None)
				if event_type == "step_started":
					print '+--', event.get("id", "step")
					print '|'
					in_event = True
				if event_type == "step_finished":
					print '|'
					print '+--', event.get("id", "step")
					print
					in_event = False
			else:
				if in_event:
					print '|  ',
				print line
		lines_shown = len(log_lines)
		install_status = json.load(opsmgr_get(stack, "/api/installation/" + str(install_id)))["status"]
		if not install_status == "running":
			break
		time.sleep(5)

def opsmgr_exec(stack, argv, stdin=None):
	command = [
		'ssh',
		'-o', 'UserKnownHostsFile=/dev/null',
		'-o', 'StrictHostKeyChecking=no',
		'-i', config.get("aws", "private-key"),
		'ubuntu@' + opsmgr_hostname(stack)
	]
	try:
		return subprocess.check_output(command + argv, stdin=stdin, stderr=subprocess.STDOUT)
	except subprocess.CalledProcessError as error:
		print 'Command failed with exit code', error.returncode
		print error.output
		sys.exit(error.returncode)

def opsmgr_import_product(stack, product, release):
	folder = product["slug"]
	print "Creating folder for product", folder
	command = [
		'mkdir', '-p', folder
	]
	opsmgr_exec(stack, command)
	files = pivnet.pivnet_files(product, release)
	for file in files:
		download_filename = os.path.basename(file["aws_object_key"])
		if not download_filename.endswith(".pivotal"):
			continue
		download_filename = folder + "/" + download_filename
		download_url = file["_links"]["download"]["href"]
		print "Downloading file", download_filename
		command = [
			'wget', '-q',
			'-O', download_filename,
			'--post-data=""',
			'--header="Authorization: Token ' + config.get('pivotal-network', 'token') + '"',
			download_url
		]
		opsmgr_exec(stack, command)
		print "Importing file", download_filename
		username = config.get("stack-" + stack["StackName"], "opsmgr-username", "admin")
		password = config.get("stack-" + stack["StackName"], "opsmgr-password", None)
		command = [
			'curl', '-k', 'https://localhost/api/products',
			'-F', 'product[file]=@' + download_filename,
			'-X', 'POST',
			'-u', username + ':' + password
		]
		opsmgr_exec(stack, command)

def opsmgr_available_products(stack):
	products = json.load(opsmgr_get(stack, "/api/products"))
	return products

def opsmgr_installed_products(stack):
	products = json.load(opsmgr_get(stack, "/api/installation_settings"))["products"]
	products = [
		{
			"guid": p["guid"],
			"name": p["identifier"],
			"product_version": p["product_version"]
		}
		for p in products
	]
	return products

def opsmgr_install_if_needed(stack, slug, product, release=None):
	available_products = opsmgr_available_products(stack)
	available_matches = [p for p in available_products if slug == p["name"]]
	if len(available_products) < 1 or (release is not None and release not in available_matches[0]["product_version"]):
		opsmgr_import(stack, product, release)
		available_products = opsmgr_available_products(stack)
		available_matches = [p for p in available_products if slug == p["name"]]

	installed_products = opsmgr_installed_products(stack)
	installed_matches = [p for p in installed_products if slug == p["name"]]
	if len(installed_matches) < 1:
		params = {
			"name": slug,
			"product_version": available_matches[0]["product_version"]
		}
		opsmgr_post(stack, "/api/installation_settings/products", urllib.urlencode(params))
	elif installed_matches[0]["product_version"] != available_matches[0]["product_version"]:
		TBD

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
	print "Waiting for Ops Manager to start ",
	opsmgr_wait(stack, verbose=True)
	print "Setting up initial Admin user"
	opsmgr_setup(stack)
	print "Configuring Ops Manager Director"
	bosh.bosh_config(stack)
	print "Ops Manager started at", opsmgr_url(stack)

def terminate_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	opsmgr_terminate_instances(stack)

def list_instances_cmd(argv):
	instances = opsmgr_find_instances()
	for i in instances:
		state = "(pending)" if i["State"]["Name"] == "pending" else ""
		print opsmgr_get_tag(i, "Stack"), "(" + opsmgr_get_tag(i, "Image") + ")", i["PublicDnsName"]

def settings_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	settings = json.load(opsmgr_get(stack, "/api/installation_settings"))
	print json.dumps(settings, indent=4)

def install_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	install_id = opsmgr_install(stack)
	opsmgr_tail_logs(stack, install_id)

def uninstall_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	install_id = opsmgr_uninstall(stack)
	opsmgr_tail_logs(stack, install_id)

def logs_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	opsmgr_tail_logs(stack)

def import_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 4 else None
	stack_name = argv[1]
	product_pattern = argv[2]
	release_pattern = argv[3]
	stack = cloudformation.select_stack(stack_name)
	product = pivnet.pivnet_select_product(product_pattern)
	release = pivnet.pivnet_select_release(product, release_pattern)
	pivnet.pivnet_accept_eula(product, release)
	opsmgr_import_product(stack, product, release)

def products_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	available_products = opsmgr_available_products(stack)
	installed_products = opsmgr_installed_products(stack)
	for ap in available_products:
		installed = [ ip for ip in installed_products if ip["name"] == ap["name"]]
		if len(installed) > 0:
			if installed[0]["product_version"] == ap["product_version"]:
				ap["installed"] = "(installed)"
			else:
				ap["installed"] = "(" + installed[0]["product_version"] + " installed)"
		else:
			ap["installed"] = ""
		print ap["name"], ap["product_version"], ap["installed"]

commands = {
	"images":    { "func": list_images_cmd,    "usage": "images [<region>]" },
	"launch":    { "func": launch_cmd,         "usage": "launch <stack-name> [<version>]" },
	"instances": { "func": list_instances_cmd, "usage": "instances" },
	"terminate": { "func": terminate_cmd,      "usage": "terminate <stack-name>" },
	"settings":  { "func": settings_cmd,       "usage": "settings <stack-name>" },
	"install":   { "func": install_cmd,        "usage": "install <stack-name>" },
	"uninstall": { "func": uninstall_cmd,      "usage": "uninstall <stack-name>" },
	"logs":      { "func": logs_cmd,           "usage": "logs <stack-name>" },
	"import":    { "func": import_cmd,         "usage": "import <stack-name> <product-name> <release-name>" },
	"products":  { "func": products_cmd,       "usage": "products <stack-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)