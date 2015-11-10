#!/usr/bin/env python
#
# Original espota.py by Ivan Grokhotkov:
# https://gist.github.com/igrr/d35ab8446922179dc58c
#
# Modified since 2015-09-18 from Pascal Gollor (https://github.com/pgollor)
# Modified since 2015-11-09 from Hristo Gochkov (https://github.com/me-no-dev)
#
# This script will push an OTA update to the ESP
# use it like: python espota.py -i <ESP_IP_address> -p <ESP_port> [-a password] -f <sketch.bin>
# Or to upload SPIFFS image:
# python espota.py -i <ESP_IP_address> -p <ESP_port> [-a password] -s -f <spiffs.bin>
#
# Changes
# 2015-09-18:
# - Add option parser.
# - Add logging.
# - Send command to controller to differ between flashing and transmitting SPIFFS image.
#
# Changes
# 2015-11-09:
# - Added digest authentication
# - Enchanced error tracking and reporting
#

from __future__ import print_function
import socket
import sys
import os
import optparse
import logging
import hashlib

# Commands
FLASH = 0
SPIFFS = 100
AUTH = 200


def serve(remoteAddr, remotePort, password, filename, command = FLASH):
  # Create a TCP/IP socket
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  serverPort = 48266
  server_address = ('0.0.0.0', serverPort)
  logging.info('Starting on %s:%s', str(server_address[0]), str(server_address[1]))
  try:
    sock.bind(server_address)
    sock.listen(1)
  except:
    logging.error("Listen Failed")
    return 1

  content_size = os.path.getsize(filename)
  f = open(filename,'rb')
  file_md5 = hashlib.md5(f.read()).hexdigest()
  f.close()
  logging.info('Upload size: %d', content_size)
  message = '%d %d %d %s\n' % (command, serverPort, content_size, file_md5)

  # Wait for a connection
  logging.info('Sending invitation to: %s', remoteAddr)
  sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  remote_address = (remoteAddr, int(remotePort))
  sent = sock2.sendto(message, remote_address)
  sock2.settimeout(10)
  try:
    data = sock2.recv(37)
  except:
    logging.error('No Answer')
    sock2.close()
    return 1
  if (data != "OK"):
    if(data.startswith('AUTH')):
      nonce = data.split()[1]
      cnonce_text = '%s%u%s%s' % (filename, content_size, file_md5, remoteAddr)
      cnonce = hashlib.md5(cnonce_text).hexdigest()
      passmd5 = hashlib.md5(password).hexdigest()
      result_text = '%s:%s:%s' % (passmd5 ,nonce, cnonce)
      result = hashlib.md5(result_text).hexdigest()
      sys.stderr.write('Authenticating...')
      sys.stderr.flush()
      message = '%d %s %s\n' % (AUTH, cnonce, result)
      sock2.sendto(message, remote_address)
      sock2.settimeout(10)
      try:
        data = sock2.recv(32)
      except:
        sys.stderr.write('FAIL\n')
        logging.error('No Answer to our Authentication')
        sock2.close()
        return 1
      if (data != "OK"):
        sys.stderr.write('FAIL\n')
        logging.error('%s', data)
        sock2.close()
        sys.exit(1);
        return 1
      sys.stderr.write('OK\n')
    else:
      logging.error('Bad Answer: %s', data)
      sock2.close()
      return 1
  sock2.close()

  logging.info('Waiting for device...')
  try:
    sock.settimeout(10)
    connection, client_address = sock.accept()
    sock.settimeout(None)
    connection.settimeout(None)
  except:
    logging.error('No response from device')
    sock.close()
    return 1

  try:
    f = open(filename, "rb")
    sys.stderr.write('Uploading')
    sys.stderr.flush()
    while True:
      chunk = f.read(1460)
      if not chunk: break
      sys.stderr.write('.')
      sys.stderr.flush()
      connection.settimeout(10)
      try:
        connection.sendall(chunk)
        res = connection.recv(4)
      except:
        sys.stderr.write('\n')
        logging.error('Error Uploading')
        connection.close()
        f.close()
        sock.close()
        return 1

    sys.stderr.write('\n')
    logging.info('Waiting for result...')
    try:
      connection.settimeout(60)
      data = connection.recv(32)
      logging.info('Result: %s' ,data)
      connection.close()
      f.close()
      sock.close()
      if (data != "OK"):
        sys.stderr.write('\n')
        logging.error('%s', data)
        return 1;
      return 0
    except:
      logging.error('No Result!')
      connection.close()
      f.close()
      sock.close()
      return 1

  finally:
    connection.close()
    f.close()

  sock.close()
  return 1
# end serve


def parser():
	parser = optparse.OptionParser(
		usage = "%prog [options]",
		description = "Transmit image over the air to the esp8266 module with OTA support."
	)

	# destination ip and port
	group = optparse.OptionGroup(parser, "Destination")
	group.add_option("-i", "--ip",
		dest = "esp_ip",
		action = "store",
		help = "ESP8266 IP Address.",
		default = False
	)
	group.add_option("-p", "--port",
		dest = "esp_port",
		type = "int",
		help = "ESP8266 ota Port. Default 8266",
		default = 8266
	)
	parser.add_option_group(group)

	# auth
	group = optparse.OptionGroup(parser, "Authentication")
	group.add_option("-a", "--auth",
		dest = "auth",
		help = "Set authentication password.",
		action = "store",
		default = ""
	)
	parser.add_option_group(group)

	# image
	group = optparse.OptionGroup(parser, "Image")
	group.add_option("-f", "--file",
		dest = "image",
		help = "Image file.",
		metavar="FILE",
		default = None
	)
	group.add_option("-s", "--spiffs",
		dest = "spiffs",
		action = "store_true",
		help = "Use this option to transmit a SPIFFS image and do not flash the module.",
		default = False
	)
	parser.add_option_group(group)

	# output group
	group = optparse.OptionGroup(parser, "Output")
	group.add_option("-d", "--debug",
		dest = "debug",
		help = "Show debug output. And override loglevel with debug.",
		action = "store_true",
		default = False
	)
	parser.add_option_group(group)

	(options, args) = parser.parse_args()

	return options
# end parser


def main(args):
	# get options
	options = parser()

	# adapt log level
	loglevel = logging.WARNING
	if (options.debug):
		loglevel = logging.DEBUG
	# end if

	# logging
	logging.basicConfig(level = loglevel, format = '%(asctime)-8s [%(levelname)s]: %(message)s', datefmt = '%H:%M:%S')

	logging.debug("Options: %s", str(options))

	# check options
	if (not options.esp_ip or not options.image):
		logging.critical("Not enough arguments.")

		return 1
	# end if

	command = FLASH
	if (options.spiffs):
		command = SPIFFS
	# end if

	return serve(options.esp_ip, options.esp_port, options.auth, options.image, command)
# end main


if __name__ == '__main__':
	sys.exit(main(sys.argv))
# end if
