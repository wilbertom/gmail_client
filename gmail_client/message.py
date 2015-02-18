import datetime
import email
import re
import time
import os
from imaplib import ParseFlags

from gmail_client.codecs import decode_email_header


def parse_flags(headers):
    """
    Parses flags from headers using Python's `ParseFlags`.

    It drops all the \ in all the flags if it exists, to
    hide the details of the protocol.

    """
    def _parse_flag(f):
        if f.startswith('\\'):
            return f[1:]
        else:
            return f

    return set(map(_parse_flag, ParseFlags(headers)))

def parse_headers(message):
    """
    We must parse the headers because Python's Message class hides a
    dictionary type object but doesn't implement all of it's methods
    like copy or iteritems.

    """
    d = {}

    for k, v in message.items():
        d[k] = v

    return d

def parse_labels(headers):
    if re.search(r'X-GM-LABELS \(([^\)]+)\)', headers):
        labels = re.search(r'X-GM-LABELS \(([^\)]+)\)', headers).groups(1)[0].split(' ')
        return map(lambda l: l.replace('"', '').decode("string_escape"), labels)
    else:
        return list()

def parse_subject(encoded_header):

    if encoded_header is not None:
        dh = encoded_header.encode('UTF-8')
    else:
        dh = ''

    return dh


class Attachment(object):
    """
    Attachments are files sent in the email.

    """

    def __init__(self, name, content_type, content):
        self.name = name
        self.content_type = content_type
        self.content = content
        self.size = 0 if content is None else len(self.content)

    def save(self, path=None):
        if path is None:
            # Save as name of attachment if there is no path specified
            path = self.name
        elif os.path.isdir(path):
            # If the path is a directory, save as name of attachment in that directory
            path = os.path.join(path, self.name)

        with open(path, 'wb') as f:
            f.write(self.content)

        return path


class ParsedEmail(object):

    def __init__(self, message):
        self._body = []
        self._html = []
        self._attachments = []

        self.parse(message)


    @staticmethod
    def is_attachment(p):
        content_disposition = p.get("Content-Disposition", None)
        filename = p.get_filename()


        if filename is not None \
                or (content_disposition is not None and
                        content_disposition.find('attachment') > -1):
            return True

        return False

    @staticmethod
    def is_multi_part(p):
        return 'multipart' == p.get_content_maintype()

    @staticmethod
    def is_html(p):
        return p.get_content_type() == 'text/html'

    @staticmethod
    def is_text(p):
        return p.get_content_type() == 'text/plain'

    def parse(self, mail):
        if self.is_multi_part(mail):
            for part in mail.walk():
                self.parse_message_part(part)

        else:
            self.parse_message_part(mail)

    def parse_message_part(self, p):
        if self.is_attachment(p):
            return self.parse_attachment(p)
        else:
            return self.parse_message(p)

    def parse_attachment(self, message_part):
        a = Attachment(decode_email_header(message_part.get_filename()),
                       message_part.get_content_type(),
                       message_part.get_payload(decode=True))

        self._attachments.append(a)
        return self

    def parse_message(self, p):
        if self.is_html(p):
            self._html.append(p)
        elif self.is_text(p):
            self._body.append(p)

    def _get_content(self, l):
        if len(l) != 0:
            # pass decode=True so that quoted printable characters
            # get interpreted into their unicode counterparts
            return l[-1].get_payload(decode=True)
        else:
            return ''

    @property
    def html(self):
        return self._get_content(self._html)

    @property
    def txt(self):
        return self._get_content(self._body)

    @property
    def attachments(self):
        return self._attachments


class Message(object):


    def __init__(self, mailbox, uid):
        self.uid = uid
        self.mailbox = mailbox
        self.gmail = mailbox.gmail if mailbox else None

        self.message = None
        self.headers = {}

        self.subject = None
        self.body = None
        self.html = None

        self.to = None
        self.fr = None
        self.cc = None
        self.delivered_to = None

        self.sent_at = None

        self._flags = set([])
        self._labels = set([])

        self.thread_id = None
        self.thread = []
        self.message_id = None
 
        self.attachments = []

    def add_flag(self, flag):
        if flag not in self.flags:
            self.gmail.imap.uid('STORE', self.uid, '+FLAGS', '\\{0}'.format(flag))
            self._flags.add(flag)

        return self

    def remove_flag(self, flag):
        if flag in self.flags:
            self.gmail.imap.uid('STORE', self.uid, '-FLAGS', '\\{0}'.format(flag))
            self._flags.remove(flag)

        return self

    @property
    def flags(self): return self._flags

    @flags.setter
    def flags(self, fs):
        self._flags = set(fs)

    @property
    def labels(self): return self._labels

    @labels.setter
    def labels(self, fs):
        self._labels = set(fs)

    @property
    def is_read(self): return 'Seen' in self.flags

    @property
    def is_starred(self): return 'Flagged' in self.flags

    @property
    def is_draft(self): return 'Draft' in self.flags

    @property
    def is_deleted(self): return 'Deleted' in self.flags

    def mark_read(self): return self.add_flag('Seen')
    def mark_unread(self): return self.remove_flag('Seen')

    def star(self): return self.add_flag('Flagged')
    def un_star(self): return self.remove_flag('Flagged')

    def move_to(self, name):
        self.gmail.copy(self.uid, name, self.mailbox.name)
        if name not in ['[Gmail]/Bin', '[Gmail]/Trash']:
            self.delete()

    def delete(self):

        if self.mailbox.name not in ['[Gmail]/Bin', '[Gmail]/Trash']:
            trash = '[Gmail]/Trash' if '[Gmail]/Trash' in self.gmail.labels() else '[Gmail]/Bin'
            self.move_to(trash)

        return self.add_flag('Deleted')

    def has_label(self, label): return label in self.labels

    def add_label(self, label):
        if label not in self.labels:
            self.gmail.imap.uid('STORE', self.uid, '+X-GM-LABELS', label)
            self.labels.add(label)
        return self

    def remove_label(self, label):
        if label in self.labels:
            self.gmail.imap.uid('STORE', self.uid, '-X-GM-LABELS', label)
            self.labels.remove(label)
        return self

    def archive(self):
        self.move_to('[Gmail]/All Mail')
        return self

    def _parse(self, raw_message):

        raw_headers = raw_message[0]
        raw_email = raw_message[1]

        self.message = email.message_from_string(raw_email)
        self.headers = parse_headers(self.message)

        self.subject = parse_subject(self.message['subject'])
        self.sent_at = datetime.datetime.fromtimestamp(time.mktime(email.utils.parsedate_tz(self.message['date'])[:9]))

        self.to = self.message['to']
        self.fr = self.message['from']
        self.delivered_to = self.message['delivered_to']

        parsed_email = ParsedEmail(self.message)
        self.body = parsed_email.txt
        self.html = parsed_email.html
        self.attachments = parsed_email.attachments

        self.flags = parse_flags(raw_headers)
        self.labels = parse_labels(raw_headers)

        if re.search(r'X-GM-THRID (\d+)', raw_headers):
            self.thread_id = re.search(r'X-GM-THRID (\d+)', raw_headers).groups(1)[0]
        if re.search(r'X-GM-MSGID (\d+)', raw_headers):
            self.message_id = re.search(r'X-GM-MSGID (\d+)', raw_headers).groups(1)[0]

    def fetch(self): return self.message if self.message else self.forced_fetch()

    @property
    def has_attachments(self):
        return len(self.attachments) > 0

    def forced_fetch(self):
        _, results = self.gmail.imap.uid('FETCH', self.uid, '(BODY.PEEK[] FLAGS X-GM-THRID X-GM-MSGID X-GM-LABELS)')
        self._parse(results[0])

        return self.message


    # returns a list of fetched messages (both sent and received) in chronological order
    def fetch_thread(self):
        self.fetch()
        original_mailbox = self.mailbox
        self.gmail.use_mailbox(original_mailbox.name)

        # fetch and cache messages from inbox or other received mailbox
        response, results = self.gmail.imap.uid('SEARCH', None, '(X-GM-THRID ' + self.thread_id + ')')
        received_messages = {}
        uids = results[0].split(' ')
        if response == 'OK':
            for uid in uids: received_messages[uid] = Message(original_mailbox, uid)
            self.gmail.fetch_multiple_messages(received_messages)
            self.mailbox.messages.update(received_messages)

        # fetch and cache messages from 'sent'
        self.gmail.use_mailbox('[Gmail]/Sent Mail')
        response, results = self.gmail.imap.uid('SEARCH', None, '(X-GM-THRID ' + self.thread_id + ')')
        sent_messages = {}
        uids = results[0].split(' ')
        if response == 'OK':
            for uid in uids: sent_messages[uid] = Message(self.gmail.mailboxes['[Gmail]/Sent Mail'], uid)
            self.gmail.fetch_multiple_messages(sent_messages)
            self.gmail.mailboxes['[Gmail]/Sent Mail'].messages.update(sent_messages)

        self.gmail.use_mailbox(original_mailbox.name)

        # combine and sort sent and received messages
        return sorted(dict(received_messages.items() + sent_messages.items()).values(), key=lambda m: m.sent_at)


