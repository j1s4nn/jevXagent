# Security Policy

## Supported Versions

Currently supported versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### DO NOT

- Open a public GitHub issue
- Disclose the vulnerability publicly before it's been addressed

### DO

1. **Email us directly** at myprojectjisan@gmail.com with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

2. **Wait for acknowledgment** - We'll respond within 48 hours

3. **Coordinate disclosure** - We'll work with you on timing

## Security Considerations

### API Keys
- Never commit API keys to the repository
- Use environment variables or config files (excluded from git)
- Rotate keys if accidentally exposed

### Proxy Security
- jevXagent runs on localhost by default (127.0.0.1)
- Do not expose the proxy to public networks without proper security
- Use HTTPS for production deployments

### Data Privacy
- jevXagent logs metrics but not request content
- API keys are never logged
- Review logs before sharing for debugging

## Security Best Practices

When using jevXagent:

1. **Keep dependencies updated** - Run `pip install --upgrade`
2. **Review configuration** - Check `~/.jevxagent/config.json` permissions
3. **Monitor logs** - Watch for suspicious activity
4. **Use latest version** - Update to get security patches
5. **Limit network exposure** - Keep proxy localhost-only

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who help improve jevXagent's security (with permission).
