# Security Policy

**Reporting address:** use GitHub's private vulnerability report link under the repository **Security** tab.

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly to avoid public disclosure. **Do not open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Go to the **Security** tab in this repository
2. Click **"Report a vulnerability"**
3. Fill in the vulnerability details:
   - **Title**: Brief description of the vulnerability
   - **Description**: Details about the issue, affected components, and potential impact
   - **Severity**: Select the appropriate severity level
   - **CVE ID**: Only if you have one (optional)

Alternatively, you can email security concerns to the repository maintainer.

### What to Expect

- Acknowledgment of your report within 48 hours
- A timeline for investigation and patch development
- Notification once a fix is released
- Credit in release notes (optional, your preference)

## Security Considerations

This is a **development prototype** and should not be deployed to production without hardening:

### Before Production Deployment

- [ ] Enable HTTPS with valid SSL/TLS certificates
- [ ] Set `DEBUG = False` in Django settings
- [ ] Use a strong, randomly generated `SECRET_KEY` stored in environment variables
- [ ] Configure PostgreSQL (not SQLite) for the database
- [ ] Enable `SECURE_SSL_REDIRECT` and HSTS headers
- [ ] Set up proper authentication and authorization checks
- [ ] Use environment variables for all secrets and credentials (never commit them)
- [ ] Enable CSRF protection and secure cookie settings
- [ ] Implement rate limiting on API endpoints
- [ ] Set up regular security updates for all dependencies (use Dependabot)
- [ ] Configure secure file uploads and storage (AWS S3, GCS, etc.)
- [ ] Implement comprehensive logging and monitoring
- [ ] Review and harden database access controls
- [ ] Conduct security testing before launch

### Dependencies

This project uses GitHub Dependabot to scan dependencies for known vulnerabilities. Keep all dependencies up to date and review security alerts regularly.

## Support

For general security questions or best-practice guidance, feel free to reach out through GitHub Discussions.
