describe('Backend security headers', () => {
  const assertSecurityHeaders = (response) => {
    expect(response.headers['x-frame-options']).to.equal('DENY');
    expect(response.headers['x-content-type-options']).to.equal('nosniff');
    expect(response.headers['referrer-policy']).to.equal('strict-origin-when-cross-origin');
    expect(response.headers['permissions-policy']).to.equal('camera=(), microphone=(), geolocation=()');
    expect(response.headers['strict-transport-security']).to.equal('max-age=31536000; includeSubDomains');
    // `blob:` is required in img-src so the navbar profile photo
    // (a URL.createObjectURL() minted from /me/photo/$value) is allowed
    // to render — issue #143.
    expect(response.headers['content-security-policy']).to.equal(
      "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' https://login.microsoftonline.com https://graph.microsoft.com; frame-ancestors 'none'",
    );
  };

  it('adds the defensive policy to successful and error responses', () => {
    cy.request('http://localhost:8000/health').then((response) => {
      expect(response.status).to.equal(200);
      assertSecurityHeaders(response);
    });

    cy.request('http://localhost:8000/api/user-data').then((response) => {
      expect(response.status).to.equal(200);
      assertSecurityHeaders(response);
    });

    cy.request({ url: 'http://localhost:8000/api/not-a-real-endpoint', failOnStatusCode: false }).then((response) => {
      expect(response.status).to.equal(404);
      assertSecurityHeaders(response);
    });
  });
});
