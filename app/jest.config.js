module.exports = {
  preset: 'react-native',
  // Native containers (incl. harmony/oh_modules) contain JS that is not part of the app.
  modulePathIgnorePatterns: ['<rootDir>/harmony/', '<rootDir>/android/'],
};
