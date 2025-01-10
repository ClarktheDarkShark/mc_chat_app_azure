const path = require('path');

module.exports = function override(config, env) {
  if (env === 'production') {
    const buildPath = path.resolve(__dirname, '../static');

    // Set output directory to ../static (one level up)
    config.output.path = buildPath;

    // Ensure publicPath points to /static to serve assets correctly
    config.output.publicPath = '/static/';

    // Ensure JS files are output directly to /js (not /static/js)
    config.output.filename = 'js/[name].[contenthash:8].js';
    config.output.chunkFilename = 'js/[name].[contenthash:8].chunk.js';

    // Adjust CSS output paths dynamically to avoid nesting issues
    const MiniCssExtractPlugin = config.plugins.find(
      (plugin) => plugin.constructor.name === 'MiniCssExtractPlugin'
    );

    if (MiniCssExtractPlugin) {
      MiniCssExtractPlugin.options.filename = 'css/[name].[contenthash:8].css';
      MiniCssExtractPlugin.options.chunkFilename = 'css/[name].[contenthash:8].chunk.css';
    }

    // Adjust other static asset paths to prevent double 'static/static' nesting
    config.plugins.forEach(plugin => {
      if (plugin.options && plugin.options.filename && plugin.options.filename.includes('static/')) {
        plugin.options.filename = plugin.options.filename.replace('static/', '');
      }
    });

    // Ensure index.html is placed directly in the build path
    config.plugins.forEach(plugin => {
      if (plugin.constructor.name === 'HtmlWebpackPlugin') {
        plugin.options.filename = path.resolve(buildPath, 'index.html');
      }
    });
  }
  return config;
};
