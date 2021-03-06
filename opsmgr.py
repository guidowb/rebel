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
		print "Launching Ops Manager instance from", image["ImageId"] + ":", image.get("Description", "-")
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
		{ "Key": "Image", "Value": image.get("Description", "-") }
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
	username = config.get("stack-" + stack["StackName"], "opsmgr-username")
	password = config.get("stack-" + stack["StackName"], "opsmgr-password")
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
	password = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(16))
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
		return
	except urllib2.HTTPError as error:
		if error.code == 422:
			return
		if error.code != 404:
			print "Error", error.code, error.reason
			sys.exit(1)
		pass
	# The PCF 1.6 and beyond API was not found (404), so we'll try the other way
	user = {
		"user[user_name]": username,
		"user[password]": password,
		"user[password_confirmation]": password
	}
	try:
		result = json.load(opsmgr_post(stack, "/api/users", urllib.urlencode(user)))
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
				try:
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
					continue
				except:
					pass
			if in_event:
				print '|  ',
			print line
		lines_shown = len(log_lines)
		install_status = json.load(opsmgr_get(stack, "/api/installation/" + str(install_id)))["status"]
		if not install_status == "running":
			break
		time.sleep(5)

def opsmgr_exec(stack, argv, stdin=None):
	keyfilepath = config.get("aws", "ssh-private-key")
	keyfilepath = os.path.expanduser(keyfilepath)
	command = [
		'ssh',
		'-q',
		'-o', 'UserKnownHostsFile=/dev/null',
		'-o', 'StrictHostKeyChecking=no',
		'-i', keyfilepath,
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
	print "Removing older versions of product", folder
	command = [
		'rm', '-f', folder + '/*'
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
		username = config.get("stack-" + stack["StackName"], "opsmgr-username")
		password = config.get("stack-" + stack["StackName"], "opsmgr-password")
		command = [
			'curl', '-k', 'https://localhost/api/products',
			'-F', 'product[file]=@' + download_filename,
			'-X', 'POST',
			'-u', username + ':' + password
		]
		opsmgr_exec(stack, command)
	opsmgr_resolve_stemcell_criteria(stack, product)

def opsmgr_available_products(stack, slug=None, release_pattern=None):
	products = json.load(opsmgr_get(stack, "/api/products"))
	if slug is not None:
		products = [p for p in products if slug == p["name"]]
	if release_pattern is not None:
		products = [p for p in products if release_pattern in p["product_version"]]
	return products

def opsmgr_installed_products(stack, slug=None):
	products = json.load(opsmgr_get(stack, "/api/installation_settings"))["products"]
	products = [
		{
			"guid": p["guid"],
			"name": p["identifier"],
			"product_version": p["product_version"]
		}
		for p in products
	]
	if slug is not None:
		products = [p for p in products if slug == p["name"]]
	return products

def opsmgr_install_if_needed(stack, slug, product_pattern, release_pattern=None):
	available_matches = opsmgr_available_products(stack, slug, release_pattern)
	if len(available_matches) < 1:
		product = pivnet.pivnet_select_product(product_pattern)
		release = pivnet.pivnet_select_release(product, release_pattern)
		opsmgr_import_product(stack, product, release)
		available_matches = opsmgr_available_products(stack, slug, release_pattern)

	installed_matches = opsmgr_installed_products(stack, slug)
	if len(installed_matches) < 1:
		params = {
			"name": slug,
			"product_version": available_matches[0]["product_version"]
		}
		opsmgr_post(stack, "/api/installation_settings/products", urllib.urlencode(params))
	elif installed_matches[0]["product_version"] != available_matches[0]["product_version"]:
		print "Upgrade not yet implemented. If you want to change the installed version,"
		print "first remove the old tile, then retry this operation."
		sys.exit(1)

def opsmgr_get_product_metadata(stack, product):
	folder = product["slug"]
	pivotal_filename = folder + "/*.pivotal"
	metadata_filename = "metadata/\\*.yml"
	command = [
		'unzip', '-p',
		pivotal_filename,
		metadata_filename
	]
	return yaml.load(opsmgr_exec(stack, command))

def opsmgr_resolve_stemcell_criteria(stack, product):
	metadata = opsmgr_get_product_metadata(stack, product)
	stemcell_criteria = metadata.get("stemcell_criteria", None)
	if stemcell_criteria is not None:
		settings = json.load(opsmgr_get(stack, "/api/installation_settings"))
		for p in settings.get("products", []):
			stemcell = p.get("stemcell", None)
			if stemcell is not None:
				if stemcell_criteria["os"] == stemcell["os"] and stemcell_criteria["version"] == stemcell["version"]:
					return
		stemcell_criteria["infrastructure"] = "aws"
		opsmgr_import_stemcell(stack, stemcell_criteria)

def opsmgr_import_stemcell(stack, stemcell):
	folder = "stemcells"
	print "Creating folder for", folder
	command = [
		'mkdir', '-p', folder
	]
	opsmgr_exec(stack, command)
	product = pivnet.pivnet_select_product("Stemcells")
	release = pivnet.pivnet_select_release(product, stemcell["version"])
	pivnet.pivnet_accept_eula(product, release)
	files = pivnet.pivnet_files(product, release)
	os_pattern = '-' + stemcell["os"] + '-'
	is_pattern = '-' + stemcell["infrastructure"] + '-'
	for file in files:
		download_filename = os.path.basename(file["aws_object_key"])
		if not os_pattern in download_filename:
			continue
		if not is_pattern in download_filename:
			continue
		download_filename = folder + "/" + download_filename
		download_url = file["_links"]["download"]["href"]
		print "Downloading stemcell", download_filename
		command = [
			'wget', '-q',
			'-O', download_filename,
			'--post-data=""',
			'--header="Authorization: Token ' + config.get('pivotal-network', 'token') + '"',
			download_url
		]
		opsmgr_exec(stack, command)
		print "Importing stemcell", download_filename
		username = config.get("stack-" + stack["StackName"], "opsmgr-username")
		password = config.get("stack-" + stack["StackName"], "opsmgr-password")
		command = [
			'curl', '-k', 'https://localhost/api/stemcells',
			'-F', 'stemcell[file]=@' + download_filename,
			'-X', 'POST',
			'-u', username + ':' + password
		]
		opsmgr_exec(stack, command)

def opsmgr_available_stemcells(stack):
	stemcells = json.load(opsmgr_get(stack, "/api/stemcells"))
	return stemcells

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

	stack_section = "stack-" + stack["StackName"]
	password = config.get(stack_section, "opsmgr-password")
	opsmgr_dns = opsmgr_hostname(stack)
	pcfelb_dns = cloudformation.get_output(stack, "PcfElbDnsName")
	sshelb_dns = cloudformation.get_output(stack, "PcfElbSshDnsName")
	app_domain = config.get("cf", "apps-domain", stack=stack_name)
	sys_domain = config.get("cf", "system-domain", stack=stack_name)
	print
	print "Ops Manager started at", opsmgr_url(stack)
	print "Admin username is admin, password is", password
	print
	print "Before proceeding to install Elastic runtime, you must create"
	print "the following records through your DNS provider:"
	print
	print "  CNAME", "opsmgr." + sys_domain, opsmgr_dns
	print "  CNAME", "*."      + app_domain, pcfelb_dns
	if app_domain != sys_domain:
		print "  CNAME", "*."      + sys_domain, pcfelb_dns
	if sshelb_dns is not None:
		print "  CNAME", "ssh."  + sys_domain, sshelb_dns
	print
	print "Failure to do so will lead to install failures later."

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

def stemcells_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	available_stemcells = opsmgr_available_stemcells(stack)
	print json.dumps(available_stemcells, indent=4)

def metadata_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 3 else None
	stack_name = argv[1]
	product_pattern = argv[2]
	stack = cloudformation.select_stack(stack_name)
	product = pivnet.pivnet_select_product(product_pattern)
	metadata = opsmgr_get_product_metadata(stack, product)
	print json.dumps(metadata, indent=4)

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
	"stemcells": { "func": stemcells_cmd,      "usage": "stemcells <stack-name>" },
	"metadata":  { "func": metadata_cmd,       "usage": "metadata <stack-name> <product-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
