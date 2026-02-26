"""
Send FCM (Firebase Cloud Messaging) to a single device token.
Uses legacy FCM HTTP API if FCM_SERVER_KEY is set in Django settings.
Otherwise no-op (call succeeds but no notification sent).
"""
import logging

logger = logging.getLogger(__name__)


def send_fcm_to_token(token, title, body, data=None):
    """
    Send a notification to one FCM token.
    token: str (User.fcm_token or Customer.fcm_token)
    title: str
    body: str
    data: optional dict for data payload
    Returns True if sent or skipped (no token), False on send error.
    """
    if not (token and str(token).strip()):
        return True
    from django.conf import settings
    server_key = getattr(settings, 'FCM_SERVER_KEY', None) or getattr(settings, 'FCM_LEGACY_SERVER_KEY', None)
    if not server_key:
        logger.info('FCM not configured (no FCM_SERVER_KEY); skipping notification')
        return True
    try:
        import urllib.request
        import json as json_module
        url = 'https://fcm.googleapis.com/fcm/send'
        payload = {
            'to': token.strip(),
            'notification': {'title': title, 'body': body},
            'priority': 'high',
        }
        if data:
            payload['data'] = {str(k): str(v) for k, v in data.items()}
        req = urllib.request.Request(
            url,
            data=json_module.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'key={server_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.getcode() < 300:
                return True
            logger.warning('FCM returned %s', resp.getcode())
            return False
    except Exception as e:
        logger.exception('FCM send failed: %s', e)
        return False
