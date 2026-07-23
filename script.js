/**
 * Personal Website - JavaScript
 * Handles config loading, navigation, smooth scrolling, theming, and reveals.
 */

document.addEventListener('DOMContentLoaded', () => {
    loadConfig();

    const navbar = document.getElementById('navbar');
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    const navLinks = document.querySelectorAll('.nav-link');
    const currentYearEl = document.getElementById('current-year');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (currentYearEl) {
        currentYearEl.textContent = new Date().getFullYear();
    }

    function setMobileMenu(isOpen) {
        if (!navToggle || !navMenu) return;

        navToggle.classList.toggle('active', isOpen);
        navToggle.setAttribute('aria-expanded', String(isOpen));
        navMenu.classList.toggle('active', isOpen);
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }

    if (navToggle) {
        navToggle.addEventListener('click', () => {
            setMobileMenu(!navMenu.classList.contains('active'));
        });
    }

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (navMenu && navMenu.classList.contains('active')) {
                setMobileMenu(false);
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && navMenu && navMenu.classList.contains('active')) {
            setMobileMenu(false);
        }
    });

    const themeToggle = document.getElementById('theme-toggle');
    const themeToggleText = themeToggle?.querySelector('.theme-toggle-text');
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme === 'tactical' || savedTheme === 'military') {
        setTacticalTheme(true);
    } else {
        setTacticalTheme(false);
    }

    function setTacticalTheme(isTactical) {
        document.body.classList.toggle('tactical-theme', isTactical);

        if (themeToggleText) {
            themeToggleText.textContent = isTactical ? 'Core Theme' : 'Tactical Theme';
        }

        if (themeToggle) {
            themeToggle.setAttribute('aria-pressed', String(isTactical));
            themeToggle.setAttribute('aria-label', isTactical ? 'Switch to Core Theme' : 'Switch to Tactical Theme');
        }
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isTactical = !document.body.classList.contains('tactical-theme');
            localStorage.setItem('theme', isTactical ? 'tactical' : 'core');
            setTacticalTheme(isTactical);
        });
    }

    function handleNavbarScroll() {
        if (!navbar) return;
        navbar.classList.toggle('scrolled', window.scrollY > 50);
    }

    window.addEventListener('scroll', handleNavbarScroll, { passive: true });
    handleNavbarScroll();

    function smoothScroll(targetId) {
        const target = document.querySelector(targetId);
        if (!target || !navbar) return;

        const navHeight = navbar.offsetHeight;
        const targetPosition = target.getBoundingClientRect().top + window.scrollY - navHeight;

        window.scrollTo({
            top: targetPosition,
            behavior: prefersReducedMotion ? 'auto' : 'smooth'
        });
    }

    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', (event) => {
            const targetId = anchor.getAttribute('href');

            if (targetId && targetId !== '#') {
                event.preventDefault();
                smoothScroll(targetId);
            }
        });
    });

    const navTargets = [...document.querySelectorAll('section[id]'), document.getElementById('contact')]
        .filter(Boolean);

    function highlightNavLink() {
        let currentId = '';
        const scrollY = window.scrollY;

        navTargets.forEach(target => {
            const targetTop = target.offsetTop - 120;
            const targetBottom = targetTop + target.offsetHeight;

            if (scrollY >= targetTop && scrollY < targetBottom) {
                currentId = target.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.toggle('active', link.getAttribute('href') === `#${currentId}`);
        });
    }

    window.addEventListener('scroll', highlightNavLink, { passive: true });
    highlightNavLink();

    if (!prefersReducedMotion) {
        const heroBackground = document.querySelector('.hero-background');

        function parallaxEffect() {
            if (heroBackground && window.innerWidth > 768) {
                heroBackground.style.transform = `translateY(${window.scrollY * 0.12}px)`;
            }
        }

        window.addEventListener('scroll', parallaxEffect, { passive: true });
    }
});

async function loadConfig() {
    try {
        const response = await fetch('config.json');

        if (!response.ok) {
            throw new Error('Failed to load config.json');
        }

        const config = await response.json();
        populatePage(config);
    } catch (error) {
        console.info('Using default HTML content (config.json not loaded)');
        initAnimations();
    }
}

function populatePage(config) {
    if (config.personal) {
        const { firstName, lastName, logoInitials, tagline } = config.personal;

        setTextContent('logo-text', logoInitials);
        setTextContent('first-name', firstName);
        setTextContent('last-name', lastName);
        setTextContent('footer-name', `${firstName} ${lastName}`);

        document.title = `${firstName} ${lastName} | AI, Robotics, Space & Defence`;

        const taglineEl = document.getElementById('tagline');
        if (taglineEl && tagline) {
            taglineEl.innerHTML = formatTagline(tagline);
        }
    }

    if (config.about) {
        const aboutText = document.getElementById('about-text');
        if (aboutText && config.about.bio) {
            aboutText.innerHTML = config.about.bio
                .map(paragraph => `<p>${escapeHTML(paragraph)}</p>`)
                .join('');
        }

        const focusGrid = document.getElementById('focus-grid');
        if (focusGrid && config.about.focusAreas) {
            focusGrid.innerHTML = config.about.focusAreas
                .map(area => `
                    <div class="focus-card">
                        <div class="focus-icon" aria-hidden="true"></div>
                        <h4>${escapeHTML(area.title)}</h4>
                        <p>${escapeHTML(area.description)}</p>
                    </div>
                `)
                .join('');
        }
    }

    const projectsGrid = document.getElementById('projects-grid');
    if (projectsGrid && config.projects) {
        projectsGrid.innerHTML = config.projects
            .map(project => {
                const title = escapeHTML(project.title);
                const link = escapeAttribute(project.link);
                const image = project.image ? escapeAttribute(project.image) : '';
                const imageCredit = project.imageCredit ? escapeHTML(project.imageCredit) : '';
                const tags = Array.isArray(project.tags) ? project.tags : [];

                return `
                    <article class="project-card">
                        <div class="project-content">
                            <div class="project-header">
                                <h3 class="project-title">${title}</h3>
                                <a href="${link}" class="project-link" aria-label="View project" target="_blank" rel="noopener noreferrer">&rarr;</a>
                            </div>
                            <p class="project-description">${escapeHTML(project.description)}</p>
                            ${image ? `
                                <a href="${link}" class="project-image-link" aria-label="View project: ${title}" target="_blank" rel="noopener noreferrer">
                                    <div class="project-image">
                                        <img src="${image}" alt="${title}" loading="lazy">
                                    </div>
                                </a>
                                ${imageCredit ? `<p class="project-image-credit">${imageCredit}</p>` : ''}
                            ` : ''}
                        </div>
                        <div class="project-tags">
                            ${tags.map(tag => `<span class="tag">${escapeHTML(tag)}</span>`).join('')}
                        </div>
                    </article>
                `;
            })
            .join('');
    }

    if (config.footer) {
        setTextContent('footer-tagline', config.footer.tagline);
    }

    initAnimations();
}

function setTextContent(id, text) {
    const element = document.getElementById(id);
    if (element && text) {
        element.textContent = text;
    }
}

function formatTagline(tagline) {
    return tagline
        .split('|')
        .map(part => escapeHTML(part.trim()))
        .join(' <span class="tagline-separator">|</span> ');
}

function initAnimations() {
    const animatedElements = document.querySelectorAll('.focus-card, .project-card');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
        animatedElements.forEach(el => el.classList.add('visible'));
        return;
    }

    const observer = new IntersectionObserver((entries, currentObserver) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                currentObserver.unobserve(entry.target);
            }
        });
    }, {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    });

    animatedElements.forEach((el, index) => {
        el.classList.add('fade-in');
        el.style.transitionDelay = `${Math.min(index * 0.05, 0.3)}s`;
        observer.observe(el);
    });
}

function escapeHTML(value = '') {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttribute(value = '') {
    return escapeHTML(value).replace(/`/g, '&#096;');
}
