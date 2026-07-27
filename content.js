(function () {
    const body = document.body;
    const themeToggle = document.getElementById('theme-toggle');
    const themeToggleText = themeToggle?.querySelector('.theme-toggle-text');
    const savedTheme = localStorage.getItem('theme');

    function setTheme(isTactical) {
        body.classList.toggle('tactical-theme', isTactical);
        if (themeToggleText) {
            themeToggleText.textContent = isTactical ? 'Core Theme' : 'Tactical Theme';
        }
        if (themeToggle) {
            themeToggle.setAttribute('aria-pressed', String(isTactical));
            themeToggle.setAttribute(
                'aria-label',
                isTactical ? 'Switch to Core Theme' : 'Switch to Tactical Theme'
            );
        }
    }

    setTheme(savedTheme === 'tactical' || savedTheme === 'military');

    themeToggle?.addEventListener('click', () => {
        const isTactical = !body.classList.contains('tactical-theme');
        localStorage.setItem('theme', isTactical ? 'tactical' : 'core');
        setTheme(isTactical);
    });

    const year = document.getElementById('current-year');
    if (year) {
        year.textContent = new Date().getFullYear();
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

    function formatDate(value, includeTime = false) {
        if (!value) return 'Date unavailable';
        const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
        const date = dateOnly
            ? new Date(...value.split('-').map((part, index) => (
                index === 1 ? Number(part) - 1 : Number(part)
            )))
            : new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return new Intl.DateTimeFormat('en-CA', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            ...(includeTime
                ? { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }
                : {})
        }).format(date);
    }

    async function loadJSON(path) {
        const response = await fetch(path, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`Could not load ${path}`);
        }
        return response.json();
    }

    async function renderNews() {
        const grid = document.getElementById('news-grid');
        const sourcesList = document.getElementById('sources-list');
        const overallUpdated = document.getElementById('news-overall-updated');
        if (!grid || !sourcesList) return;

        try {
            const data = await loadJSON('data/news.json');
            if (overallUpdated) {
                overallUpdated.textContent = `Updated ${formatDate(data.generatedAt, true)}`;
            }

            grid.innerHTML = data.topics.map(topic => {
                const stories = topic.stories.length
                    ? topic.stories.map(story => `
                        <li>
                            <a href="${escapeAttribute(story.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(story.title)}</a>
                            <span class="story-meta">(${escapeHTML(formatDate(story.publishedAt))}, ${escapeHTML(story.source)})</span>
                        </li>
                    `).join('')
                    : '<li class="empty-story">No current stories available.</li>';

                return `
                    <article class="news-card">
                        <header>
                            <h3>${escapeHTML(topic.name)}</h3>
                            <p>Last updated ${escapeHTML(formatDate(topic.updatedAt, true))}</p>
                        </header>
                        <ol>${stories}</ol>
                    </article>
                `;
            }).join('');

            const groupedSources = data.sources.reduce((groups, source) => {
                groups[source.topic] = groups[source.topic] || [];
                groups[source.topic].push(source);
                return groups;
            }, {});

            sourcesList.innerHTML = Object.entries(groupedSources)
                .map(([topic, sources]) => `
                    <div class="source-group">
                        <h3>${escapeHTML(topic)}</h3>
                        <ul>
                            ${sources.map(source => `
                                <li><a href="${escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.name)}</a></li>
                            `).join('')}
                        </ul>
                    </div>
                `).join('');
        } catch (error) {
            grid.innerHTML = '<p class="content-status content-error">The news feed is temporarily unavailable.</p>';
            sourcesList.innerHTML = '';
            console.error(error);
        }
    }

    async function renderFieldNotes() {
        const grid = document.getElementById('notes-grid');
        if (!grid) return;

        try {
            const data = await loadJSON('data/field-notes.json');
            grid.innerHTML = data.posts.length
                ? data.posts.map(post => `
                    <article class="note-card">
                        <div class="note-card-meta">
                            <time datetime="${escapeAttribute(post.date)}">${escapeHTML(formatDate(post.date))}</time>
                            ${post.sample ? '<span>Sample</span>' : ''}
                        </div>
                        <h2><a href="${escapeAttribute(post.url)}">${escapeHTML(post.title)}</a></h2>
                        <p>${escapeHTML(post.summary)}</p>
                        <div class="note-tags">
                            ${post.tags.map(tag => `<span class="tag">${escapeHTML(tag)}</span>`).join('')}
                        </div>
                    </article>
                `).join('')
                : '<p class="content-status">No Field Notes have been published yet.</p>';
        } catch (error) {
            grid.innerHTML = '<p class="content-status content-error">Field Notes are temporarily unavailable.</p>';
            console.error(error);
        }
    }

    if (body.dataset.contentPage === 'news') {
        renderNews();
    } else if (body.dataset.contentPage === 'field-notes') {
        renderFieldNotes();
    }
}());
