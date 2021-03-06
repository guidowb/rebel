#!/usr/bin/env python

import sys
import os
import stat
import errno
import urllib
import zipfile
import subprocess

HOME_DIR = os.path.expanduser("~")
AWS_CLI_DIR = HOME_DIR + "/.aws-cli"
AWS_CLI_BIN = AWS_CLI_DIR + "/bin/aws"
AWS_CLI_ZIP = AWS_CLI_DIR + "/aws.zip"
AWS_CLI_URL = "https://s3.amazonaws.com/aws-cli/awscli-bundle.zip"
AWS_CLI_INSTALL = AWS_CLI_DIR + "/awscli-bundle/install"

def aws_cli(argv):
	install_aws_cli_if_required()
	verify_region(argv)
	command = [
		AWS_CLI_BIN,
		'--no-paginate',
		'--output', 'json'
	]
	return subprocess.check_output(command + argv, stderr=subprocess.STDOUT)

def aws_cli_verbose(argv):
	try:
		return aws_cli(argv)
	except subprocess.CalledProcessError as error:
		print ' '.join(argv)
		print 'Command failed with exit code', error.returncode
		print error.output
		sys.exit(error.returncode)

def install_aws_cli_if_required():
	if os.path.isfile(AWS_CLI_BIN) and os.access(AWS_CLI_BIN, os.X_OK):
		return
	print "Installing AWS CLI"
	mkdir_p(AWS_CLI_DIR)
	print "   Downloading latest"
	urllib.urlretrieve(AWS_CLI_URL, AWS_CLI_ZIP)
	print "   Extracting"
	zipfile.ZipFile(AWS_CLI_ZIP, 'r').extractall(AWS_CLI_DIR)
	print "   Installing"
	os.chmod(AWS_CLI_INSTALL, stat.S_IXUSR | stat.S_IRUSR)
	subprocess.check_output([AWS_CLI_INSTALL, "-i", AWS_CLI_DIR])
	version = subprocess.check_output([AWS_CLI_BIN, "--version"], stderr=subprocess.STDOUT).rstrip()
	print "   Version:", version
	print "   Done"

def get_s3_endpoint(region):
	if region == 'us-east-1':
		return 'http://s3.amazonaws.com'
	return 'http://s3-' + region + '.amazonaws.com'

def verify_region(argv):
	command = [
		AWS_CLI_BIN,
		'configure', 'get', 'region'
	]
	region = subprocess.check_output(command, stderr=subprocess.STDOUT)
	segments = region.strip().split('-')
	if len(region) < 1:
		print "aws region must be specified"
	elif len(segments) < 3 or len(segments[2]) > 1:
		print "your aws region is set to", region
		print "aws region must be of the form xx-yyyyy-n"
		if len(segments) > 2 and len(segments[2]) > 1:
			print "and the last part must specify a region number but no availability zone letter"
	else:
		return
	print 'use "aws configure set region <region>" to fix your region before proceeding'
	sys.exit(1)

def mkdir_p(dir):
	try:
		os.makedirs(dir)
	except os.error, e:
		if e.errno != errno.EEXIST:
			raise

def main(argv):
	install_aws_cli_if_required()
	os.execv(AWS_CLI_BIN, [ 'aws' ] + argv[1:])

if __name__ == '__main__':
	main(sys.argv)