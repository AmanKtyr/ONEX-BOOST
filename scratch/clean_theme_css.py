# Helper CSS to seamlessly integrate with Webflow's kreme-template.webflow.shared.fcd42b28c.min.css
custom_css = """/* Brun Haus Theme Additions for ONEX BOOST */
.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font--main-font);
  font-size: 1.8rem;
  letter-spacing: -0.02em;
  text-transform: uppercase;
}

.brand-badge {
  font-family: var(--font--second-font);
  font-size: 0.65rem;
  font-weight: 700;
  padding: 0.2rem 0.5rem;
  border-radius: var(--padding-radius--borders-radius);
  background: var(--colors--soft-yellow);
  color: var(--colors--dark-green);
  letter-spacing: 0.05em;
  margin-left: 0.4rem;
}

/* Ensure images in product cards are crisp and properly centered */
.product-image {
  object-fit: contain;
  transition: transform 0.4s ease;
}

.product-container:hover .product-image {
  transform: scale(1.08);
}

/* Mobile Nav Drawer compatibility */
@media screen and (max-width: 991px) {
  .nav-menu {
    border-radius: var(--padding-radius--borders-radius);
  }
}

/* Form input styling harmonized with Brun Haus */
.text-field-contact {
  background-color: transparent;
  border: none;
  border-bottom: 2px solid var(--colors--dark-green);
  border-radius: 0;
  color: var(--colors--dark-green);
  font-family: var(--font--second-font);
  font-size: 1.1rem;
  padding: 0.75rem 0;
  width: 100%;
  margin-bottom: 1.5rem;
  outline: none;
  transition: border-color 0.25s ease;
}

.text-field-contact:focus {
  border-bottom-color: #000;
}

.contact-button {
  border-radius: var(--padding-radius--borders-radius);
  background-color: var(--colors--dark-green);
  color: var(--colors--white);
  padding: 0.8rem 1.6rem;
  font-family: var(--font--second-font);
  font-weight: 600;
  font-size: 1rem;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.contact-button:hover {
  background-color: #022b15;
}
"""

with open('static/css/brunhaus-theme.css', 'w', encoding='utf-8') as f:
    f.write(custom_css)
print("Cleaned brunhaus-theme.css successfully")
